"""
VABB primary node - FastAPI server with transparent task distribution
Enhanced with: task tracking, node monitoring, real-time dashboard
"""

from __future__ import annotations

import csv
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum
from collections import deque, defaultdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import requests

# -----------------------------
# Configuration
# -----------------------------
DATA_FILE = Path(__file__).with_name("sample_runway_data.csv")
WINDOW_MINUTES = 60
CYCLE_SECONDS = 45
TASKS_PER_CYCLE = 5
AIRPORT_CODE = "VABB"
AIRPORT_IATA = "BOM"
RUNWAY = "09/27"
AVIATIONSTACK_ACCESS_KEY = os.getenv("AVIATIONSTACK_ACCESS_KEY")
AVIATIONSTACK_BASE_URL = "https://api.aviationstack.com/v1/flights"
AVIATIONSTACK_MIN_FETCH_SECONDS = 300
DEFAULT_OCCUPANCY_SECONDS = 75
NODE_TIMEOUT_SECONDS = 30  # Consider node dead if no heartbeat for 30s
TASK_TIMEOUT_SECONDS = 60  # Task considered stale if not completed in 60s
WORKING_GRACE_SECONDS = 5  # Keep node in WORKING briefly after activity

# -----------------------------
# Logging
# -----------------------------
LOG_FILE = Path(__file__).with_name("edge_feedback.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vabb-node")

# -----------------------------
# Task Status Tracking
# -----------------------------
class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class Task:
    task_id: str
    type: str
    node_id: Optional[str]
    status: TaskStatus
    created_at: datetime
    assigned_at: Optional[datetime]
    completed_at: Optional[datetime]
    window_minutes: int
    result: Optional[Dict[str, Any]] = None
    task_data: Optional[Dict[str, Any]] = None


@dataclass
class NodeInfo:
    node_id: str
    last_heartbeat: datetime
    last_active_at: datetime
    status: str  # "alive", "dead", "idle", "working"
    tasks_assigned: int
    tasks_completed: int
    tasks_failed: int
    current_task: Optional[str]


# -----------------------------
# Data Models
# -----------------------------
class EdgeFeedback(BaseModel):
    decision: str = Field(..., description="Edge node congestion decision")
    notes: Optional[str] = Field(None, description="Optional notes from edge")
    timestamp_utc: Optional[str] = Field(
        None, description="Optional edge timestamp in ISO-8601"
    )


@dataclass
class TrafficRow:
    timestamp_utc: datetime
    movement_type: str
    runway: str
    occupancy_seconds: int


# -----------------------------
# Task and Node Management
# -----------------------------
class DistributedTaskManager:
    """Manages task distribution and node tracking with full transparency"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, Task] = {}
        self._nodes: Dict[str, NodeInfo] = {}
        self._task_queue: deque = deque()
        self._task_counter = 0
        self._latest_result: Optional[Dict[str, Any]] = None
        self._history: deque = deque(maxlen=50)

    def _extract_metrics(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not result:
            return None
        # Accept both schemas: nested "result" or flat metrics.
        if "result" in result and isinstance(result["result"], dict):
            return result["result"]
        return result

    def _classify_congestion(self, density: float, occupancy: float) -> str:
        if density > 30 or occupancy > 70:
            return "high"
        if density > 15 or occupancy > 40:
            return "medium"
        return "low"

    def _build_xai(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        density = metrics.get("traffic_density")
        occupancy = metrics.get("runway_occupancy_percent")
        min_spacing = metrics.get("min_spacing_minutes")
        arrivals = metrics.get("arrivals")
        departures = metrics.get("departures")
        total = metrics.get("total_movements")
        congestion_score = metrics.get("congestion_score")
        congestion_level = metrics.get("congestion_level")

        reasons = []
        if density is not None:
            if density > 30:
                reasons.append("High traffic density (>30/hr)")
            elif density > 15:
                reasons.append("Moderate traffic density (1530/hr)")
            else:
                reasons.append("Low traffic density (<=15/hr)")
        if occupancy is not None:
            if occupancy > 70:
                reasons.append("High runway occupancy (>70%)")
            elif occupancy > 40:
                reasons.append("Moderate runway occupancy (4070%)")
            else:
                reasons.append("Low runway occupancy (<=40%)")
        if min_spacing is not None and min_spacing > 0:
            if min_spacing < 3.0:
                reasons.append("Tight spacing (<3 min) increases score")
            else:
                reasons.append("Spacing acceptable (>=3 min)")

        imbalance = None
        if total and arrivals is not None and departures is not None and total > 0:
            arrival_pct = (arrivals / total) * 100
            imbalance = abs(arrival_pct - 50.0)
            if imbalance > 30:
                reasons.append("High arrival/departure imbalance (>30%)")

        return {
            "congestion_level": congestion_level,
            "congestion_score": congestion_score,
            "reasons": reasons,
            "signals": {
                "traffic_density_per_hr": density,
                "runway_occupancy_percent": occupancy,
                "min_spacing_minutes": min_spacing,
                "arrival_departure_imbalance_pct": round(imbalance, 1) if imbalance is not None else None,
            },
            "thresholds": {
                "density_high": 30,
                "density_medium": 15,
                "occupancy_high_percent": 70,
                "occupancy_medium_percent": 40,
                "spacing_penalty_minutes": 3.0,
            },
        }

    def _build_forecast(self) -> Optional[Dict[str, Any]]:
        if not self._history:
            return None
        # Use last N points for a simple moving average forecast.
        window = list(self._history)[-5:]
        def avg(key: str) -> Optional[float]:
            vals = [m.get(key) for m in window if m.get(key) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        density = avg("traffic_density")
        occupancy = avg("runway_occupancy_percent")
        arrivals = avg("arrivals")
        departures = avg("departures")
        score = avg("congestion_score")

        predicted_level = None
        if density is not None and occupancy is not None:
            predicted_level = self._classify_congestion(density, occupancy)

        return {
            "method": "moving_average",
            "window_points": len(window),
            "predicted_congestion_level": predicted_level,
            "predicted_congestion_score": score,
            "predicted_traffic_density_per_hr": density,
            "predicted_runway_occupancy_percent": occupancy,
            "predicted_arrivals": arrivals,
            "predicted_departures": departures,
        }
        
    def register_node(self, node_id: str) -> None:
        """Register or update node heartbeat"""
        with self._lock:
            now = datetime.now(timezone.utc)
            if node_id not in self._nodes:
                self._nodes[node_id] = NodeInfo(
                    node_id=node_id,
                    last_heartbeat=now,
                    last_active_at=now,
                    status="alive",
                    tasks_assigned=0,
                    tasks_completed=0,
                    tasks_failed=0,
                    current_task=None
                )
                logger.info(f" New node registered: {node_id}")
            else:
                self._nodes[node_id].last_heartbeat = now
                # Update status based on heartbeat
                if self._nodes[node_id].current_task is None:
                    self._nodes[node_id].status = "idle"
                else:
                    self._nodes[node_id].status = "working"
    
    def create_task(self, task_type: str, window_minutes: int, data: Optional[Dict[str, Any]] = None) -> str:
        """Create a new task and add to queue"""
        with self._lock:
            self._task_counter += 1
            task_id = f"task-{self._task_counter:05d}"
            now = datetime.now(timezone.utc)
            
            task = Task(
                task_id=task_id,
                type=task_type,
                node_id=None,
                status=TaskStatus.PENDING,
                created_at=now,
                assigned_at=None,
                completed_at=None,
                window_minutes=window_minutes,
                result=None,
                task_data=data
            )
            
            self._tasks[task_id] = task
            self._task_queue.append(task_id)
            
            logger.info(f" Task created: {task_id} (type: {task_type})")
            return task_id
    
    def get_next_task(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Assign next task to requesting node"""
        with self._lock:
            if not self._task_queue:
                return None
            
            task_id = self._task_queue.popleft()
            task = self._tasks[task_id]
            now = datetime.now(timezone.utc)
            
            # Update task
            task.node_id = node_id
            task.status = TaskStatus.ASSIGNED
            task.assigned_at = now
            
            # Update node
            if node_id in self._nodes:
                self._nodes[node_id].tasks_assigned += 1
                self._nodes[node_id].current_task = task_id
                self._nodes[node_id].status = "working"
                self._nodes[node_id].last_active_at = now
            
            logger.info(f" Task {task_id} assigned to {node_id}")
            
            # Include task data in response
            task_payload = {
                "task_id": task_id,
                "type": task.type,
                "window_minutes": task.window_minutes,
                "assigned_at": task.assigned_at.isoformat(),
                "node_id": node_id
            }
            
            # Add task-specific data if available
            if task.task_data:
                task_payload["data"] = task.task_data
            
            return task_payload
    
    def complete_task(self, task_id: str, node_id: str, result: Dict[str, Any]) -> None:
        """Mark task as completed"""
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f" Unknown task completion: {task_id}")
                return
            
            task = self._tasks[task_id]
            now = datetime.now(timezone.utc)
            
            task.status = TaskStatus.COMPLETED
            task.completed_at = now
            task.result = result
            self._latest_result = result
            metrics = self._extract_metrics(result)
            if metrics:
                self._history.append(metrics)
            
            # Update node
            if node_id in self._nodes:
                self._nodes[node_id].tasks_completed += 1
                self._nodes[node_id].current_task = None
                self._nodes[node_id].status = "idle"
                self._nodes[node_id].last_active_at = now
            
            duration = (now - task.assigned_at).total_seconds() if task.assigned_at else 0
            logger.info(f" Task {task_id} completed by {node_id} in {duration:.1f}s")
    
    def fail_task(self, task_id: str, node_id: str, reason: str) -> None:
        """Mark task as failed"""
        with self._lock:
            if task_id not in self._tasks:
                return
            
            task = self._tasks[task_id]
            now = datetime.now(timezone.utc)
            
            task.status = TaskStatus.FAILED
            task.completed_at = now
            task.result = {"error": reason}
            
            if node_id in self._nodes:
                self._nodes[node_id].tasks_failed += 1
                self._nodes[node_id].current_task = None
                self._nodes[node_id].status = "idle"
                self._nodes[node_id].last_active_at = now
            
            logger.warning(f" Task {task_id} failed on {node_id}: {reason}")
    
    def check_timeouts(self) -> None:
        """Check for timed out tasks and dead nodes"""
        with self._lock:
            now = datetime.now(timezone.utc)
            
            # Check for dead nodes
            for node_id, node in self._nodes.items():
                if (now - node.last_heartbeat).total_seconds() > NODE_TIMEOUT_SECONDS:
                    if node.status != "dead":
                        node.status = "dead"
                        logger.warning(f" Node {node_id} marked as dead (no heartbeat)")
            
            # Check for timed out tasks
            for task_id, task in self._tasks.items():
                if task.status == TaskStatus.ASSIGNED and task.assigned_at:
                    if (now - task.assigned_at).total_seconds() > TASK_TIMEOUT_SECONDS:
                        task.status = TaskStatus.TIMEOUT
                        logger.warning(f" Task {task_id} timed out on {task.node_id}")
                        # Re-queue the task
                        task.status = TaskStatus.PENDING
                        task.node_id = None
                        task.assigned_at = None
                        self._task_queue.append(task_id)
                        logger.info(f" Task {task_id} re-queued after timeout")
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        with self._lock:
            now = datetime.now(timezone.utc)
            latest_completed_from_tasks = None
            for t in sorted(self._tasks.values(), key=lambda x: x.created_at, reverse=True):
                if t.status == TaskStatus.COMPLETED and t.result:
                    latest_completed_from_tasks = t.result
                    break

            # Map currently assigned tasks to nodes for accurate working status
            assigned_by_node: Dict[str, str] = {}
            for t in self._tasks.values():
                if t.status == TaskStatus.ASSIGNED and t.node_id:
                    assigned_by_node[t.node_id] = t.task_id
            
            # Node statistics (derive status from heartbeat + current_task for accuracy)
            for n in self._nodes.values():
                if (now - n.last_heartbeat).total_seconds() > NODE_TIMEOUT_SECONDS:
                    n.status = "dead"
                elif n.node_id in assigned_by_node:
                    n.current_task = assigned_by_node[n.node_id]
                    n.status = "working"
                elif (now - n.last_active_at).total_seconds() <= WORKING_GRACE_SECONDS:
                    n.status = "working"
                else:
                    n.status = "idle"

            alive_nodes = [n for n in self._nodes.values() if n.status in ["idle", "working"]]
            working_nodes = [n for n in self._nodes.values() if n.status == "working"]
            dead_nodes = [n for n in self._nodes.values() if n.status == "dead"]
            
            # Task statistics
            pending_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
            assigned_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.ASSIGNED]
            completed_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]
            failed_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.FAILED]
            
            xai = None
            latest_metrics = self._extract_metrics(self._latest_result) if self._latest_result else None
            if latest_metrics:
                xai = self._build_xai(latest_metrics)
            forecast = self._build_forecast()

            return {
                "timestamp": now.isoformat(),
                "server_file": __file__,
                "node_timeout_seconds": NODE_TIMEOUT_SECONDS,
                "working_grace_seconds": WORKING_GRACE_SECONDS,
                "nodes": {
                    "total": len(self._nodes),
                    "alive": len(alive_nodes),
                    "working": len(working_nodes),
                    "dead": len(dead_nodes),
                    "details": [
                        {
                            "node_id": n.node_id,
                            "status": n.status,
                            "last_heartbeat": n.last_heartbeat.isoformat(),
                            "last_active_at": n.last_active_at.isoformat(),
                            "seconds_since_heartbeat": (now - n.last_heartbeat).total_seconds(),
                            "seconds_since_activity": (now - n.last_active_at).total_seconds(),
                            "tasks_assigned": n.tasks_assigned,
                            "tasks_completed": n.tasks_completed,
                            "tasks_failed": n.tasks_failed,
                            "current_task": n.current_task
                        }
                        for n in self._nodes.values()
                    ]
                },
                "tasks": {
                    "total": len(self._tasks),
                    "pending": len(pending_tasks),
                    "assigned": len(assigned_tasks),
                    "completed": len(completed_tasks),
                    "failed": len(failed_tasks),
                    "queue_size": len(self._task_queue),
                    "recent_tasks": [
                        {
                            "task_id": t.task_id,
                            "type": t.type,
                            "status": t.status.value,
                            "node_id": t.node_id,
                            "created_at": t.created_at.isoformat(),
                            "assigned_at": t.assigned_at.isoformat() if t.assigned_at else None,
                            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                            "duration_seconds": (
                                (t.completed_at - t.assigned_at).total_seconds()
                                if t.completed_at and t.assigned_at else None
                            ),
                            "window_minutes": t.window_minutes,
                            "task_data_summary": {
                                "traffic_movements": len(t.task_data.get("traffic_movements", [])) if t.task_data else None,
                                "window_start": t.task_data.get("window_start") if t.task_data else None,
                                "window_end": t.task_data.get("window_end") if t.task_data else None,
                                "airport_code": t.task_data.get("airport_code") if t.task_data else None,
                                "runway": t.task_data.get("runway") if t.task_data else None,
                            },
                            "result_summary": (
                                {
                                    "congestion_level": (
                                        t.result.get("result", t.result).get("congestion_level")
                                        if t.result else None
                                    ),
                                    "congestion_score": (
                                        t.result.get("result", t.result).get("congestion_score")
                                        if t.result else None
                                    ),
                                    "total_movements": (
                                        t.result.get("result", t.result).get("total_movements")
                                        if t.result else None
                                    ),
                                    "traffic_density": (
                                        t.result.get("result", t.result).get("traffic_density")
                                        if t.result else None
                                    ),
                                    "runway_occupancy_percent": (
                                        t.result.get("result", t.result).get("runway_occupancy_percent")
                                        if t.result else None
                                    ),
                                } if t.result else None
                            ),
                        }
                        for t in sorted(self._tasks.values(), key=lambda x: x.created_at, reverse=True)[:20]
                    ]
                },
                "latest_result": self._latest_result,
                "latest_result_from_tasks": latest_completed_from_tasks,
                "latest_result_present": self._latest_result is not None,
                "latest_metrics": latest_metrics,
                "xai": xai,
                "forecast": forecast
            }


# -----------------------------
# Data Loading and Generation
# -----------------------------
class DataLoader:
    def __init__(self, path: Path):
        self.path = path

    def _parse_row(self, row: Dict[str, str]) -> TrafficRow:
        ts = datetime.fromisoformat(row["timestamp_utc"]).replace(tzinfo=timezone.utc)
        return TrafficRow(
            timestamp_utc=ts,
            movement_type=row["movement_type"],
            runway=row["runway"],
            occupancy_seconds=int(row["occupancy_seconds"]),
        )

    def load(self) -> List[TrafficRow]:
        if not self.path.exists():
            return []
        rows: List[TrafficRow] = []
        with self.path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rows.append(self._parse_row(row))
                except Exception:
                    continue
        return rows


class DataGenerator:
    def __init__(self, path: Path):
        self.path = path

    def generate(self, hours: int = 2, interval_minutes: int = 5) -> None:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)

        rows: List[TrafficRow] = []
        current = start
        while current <= now:
            # Realistic traffic patterns based on time of day
            hour = current.hour
            
            # Peak hours: 6-9 AM and 5-8 PM (higher traffic)
            if (6 <= hour <= 9) or (17 <= hour <= 20):
                traffic_probability = 0.9
                base_occupancy = 80
            # Night hours: 11 PM - 5 AM (lower traffic)
            elif hour >= 23 or hour <= 5:
                traffic_probability = 0.3
                base_occupancy = 50
            # Normal hours
            else:
                traffic_probability = 0.65
                base_occupancy = 65
            
            if random.random() < traffic_probability:
                # Realistic arrival/departure ratio (slightly more arrivals in morning, departures in evening)
                if 6 <= hour <= 12:
                    arrival_chance = 0.6
                elif 17 <= hour <= 21:
                    arrival_chance = 0.4
                else:
                    arrival_chance = 0.5
                    
                movement_type = "arrival" if random.random() < arrival_chance else "departure"
                
                # More realistic occupancy with variation
                occupancy_seconds = base_occupancy + random.randint(-20, 40)
                occupancy_seconds = max(30, min(180, occupancy_seconds))  # Clamp between 30-180s
                
                rows.append(
                    TrafficRow(
                        timestamp_utc=current,
                        movement_type=movement_type,
                        runway=RUNWAY,
                        occupancy_seconds=occupancy_seconds,
                    )
                )
            current += timedelta(minutes=interval_minutes)

        with self.path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["timestamp_utc", "movement_type", "runway", "occupancy_seconds"]
            )
            for r in rows:
                writer.writerow(
                    [
                        r.timestamp_utc.isoformat(),
                        r.movement_type,
                        r.runway,
                        r.occupancy_seconds,
                    ]
                )


# -----------------------------
# Metrics Calculation
# -----------------------------
class MetricsCalculator:
    def compute(
        self, rows: List[TrafficRow], window_minutes: int, now: datetime
    ) -> Dict[str, Any]:
        window_start = now - timedelta(minutes=window_minutes)
        window_rows = [r for r in rows if r.timestamp_utc >= window_start]

        arrivals = sum(1 for r in window_rows if r.movement_type == "arrival")
        departures = sum(1 for r in window_rows if r.movement_type == "departure")
        total = arrivals + departures

        window_hours = window_minutes / 60.0
        window_seconds = window_minutes * 60.0

        traffic_density = total / window_hours if window_hours > 0 else 0.0
        arrival_rate = arrivals / window_hours if window_hours > 0 else 0.0
        departure_rate = departures / window_hours if window_hours > 0 else 0.0

        occupancy_seconds = sum(r.occupancy_seconds for r in window_rows)
        estimated_runway_occupancy = (
            occupancy_seconds / window_seconds if window_seconds > 0 else 0.0
        )
        estimated_runway_occupancy = min(1.0, estimated_runway_occupancy)

        congestion_level = self._classify_congestion(traffic_density, estimated_runway_occupancy)

        return {
            "airport": AIRPORT_CODE,
            "runway": RUNWAY,
            "timestamp_utc": now.isoformat(),
            "window_minutes": window_minutes,
            "traffic_density": round(traffic_density, 2),
            "arrival_rate": round(arrival_rate, 2),
            "departure_rate": round(departure_rate, 2),
            "estimated_runway_occupancy": round(estimated_runway_occupancy, 2),
            "congestion_level": congestion_level,
            "total_movements": total,
        }

    def _classify_congestion(self, density: float, occupancy: float) -> str:
        if density > 30 or occupancy > 0.7:
            return "high"
        if density > 15 or occupancy > 0.4:
            return "medium"
        return "low"


# -----------------------------
# Summary Store
# -----------------------------
class SummaryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._summary: Optional[Dict[str, Any]] = None

    def set(self, summary: Dict[str, Any]) -> None:
        with self._lock:
            self._summary = summary

    def get(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._summary


# -----------------------------
# Background Tasks
# -----------------------------
class CongestionEngine:
    def __init__(self, data_file: Path, store: SummaryStore, task_manager: DistributedTaskManager):
        self.data_file = data_file
        self.store = store
        self.task_manager = task_manager
        self.loader = DataLoader(data_file)
        self.generator = DataGenerator(data_file)
        self.calculator = MetricsCalculator()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _ensure_recent_data(self) -> None:
        rows = self.loader.load()
        if not rows:
            self.generator.generate()
            return

        now = datetime.now(timezone.utc)
        # Ensure we have data within the active window, not just "last 24h".
        window_rows = [r for r in rows if r.timestamp_utc >= now - timedelta(minutes=WINDOW_MINUTES)]
        if not window_rows:
            self.generator.generate()

    def _cycle(self) -> None:
        while not self._stop_event.is_set():
            self._ensure_recent_data()
            now = datetime.now(timezone.utc)
            rows = self.loader.load()
            summary = self.calculator.compute(rows, WINDOW_MINUTES, now)
            self.store.set(summary)
            
            # Prepare traffic data for analysis task
            window_start = now - timedelta(minutes=WINDOW_MINUTES)
            recent_rows = [r for r in rows if r.timestamp_utc >= window_start]
            if not recent_rows:
                # Regenerate once if the file is stale for the active window.
                self.generator.generate()
                rows = self.loader.load()
                recent_rows = [r for r in rows if r.timestamp_utc >= window_start]
            
            if recent_rows:
                # Convert traffic rows to serializable format
                traffic_data = [
                    {
                        "timestamp_utc": r.timestamp_utc.isoformat(),
                        "movement_type": r.movement_type,
                        "runway": r.runway,
                        "occupancy_seconds": r.occupancy_seconds
                    }
                    for r in recent_rows
                ]
                
                # Generate task with real traffic data
                task_data = {
                    "traffic_movements": traffic_data,
                    "window_start": window_start.isoformat(),
                    "window_end": now.isoformat(),
                    "airport_code": AIRPORT_CODE,
                    "runway": RUNWAY
                }
                
                for _ in range(TASKS_PER_CYCLE):
                    self.task_manager.create_task("compute_congestion", WINDOW_MINUTES, task_data)
            else:
                logger.warning(" No traffic data in window; skipping task creation this cycle")
            
            # Check for timeouts
            self.task_manager.check_timeouts()
            
            time.sleep(CYCLE_SECONDS)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._cycle, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()


# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="VABB Primary Node - Distributed Task System")
store = SummaryStore()
task_manager = DistributedTaskManager()
engine = CongestionEngine(DATA_FILE, store, task_manager)


@app.on_event("startup")
def on_startup() -> None:
    logger.info(" Server file: %s", __file__)
    engine._ensure_recent_data()
    now = datetime.now(timezone.utc)
    rows = engine.loader.load()
    summary = engine.calculator.compute(rows, WINDOW_MINUTES, now)
    store.set(summary)
    engine.start()
    logger.info(" Server started - distributed task system online")


@app.get("/")
def root():
    """Redirect to dashboard"""
    return HTMLResponse("""
    <html>
        <head><meta http-equiv="refresh" content="0; url=/dashboard"></head>
        <body>Redirecting to dashboard...</body>
    </html>
    """)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Real-time monitoring dashboard"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>VABB Distributed Task Monitor</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                padding: 20px;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 30px;
                border-radius: 12px;
                margin-bottom: 20px;
                box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
            }
            h1 { font-size: 2em; margin-bottom: 10px; }
            .subtitle { opacity: 0.9; font-size: 1.1em; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card {
                background: #1e293b;
                padding: 20px;
                border-radius: 8px;
                border: 1px solid #334155;
            }
            .card h2 {
                font-size: 1.2em;
                margin-bottom: 15px;
                color: #a78bfa;
            }
            .stat {
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid #334155;
            }
            .stat:last-child { border-bottom: none; }
            .stat-label { color: #94a3b8; }
            .stat-value { font-weight: bold; }
            .status-alive { color: #10b981; }
            .status-working { color: #3b82f6; }
            .status-dead { color: #ef4444; }
            .status-idle { color: #fbbf24; }
            .status-pending { color: #fbbf24; }
            .status-completed { color: #10b981; }
            .status-failed { color: #ef4444; }
            .node-item, .task-item {
                background: #0f172a;
                padding: 12px;
                margin: 10px 0;
                border-radius: 6px;
                border-left: 4px solid #667eea;
            }
            .timestamp {
                font-size: 0.9em;
                color: #64748b;
                margin-top: 5px;
            }
            .auto-refresh {
                position: fixed;
                top: 20px;
                right: 20px;
                background: #10b981;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 0.9em;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
        </style>
    </head>
    <body>
        <div class="auto-refresh"> Auto-refreshing</div>
        
        <div class="header">
            <h1> VABB Distributed Task Monitor</h1>
            <div class="subtitle">Real-time task distribution between Mac & Phone nodes</div>
        </div>

        <div id="content">Loading...</div>

        <script>
            async function fetchStatus() {
                const response = await fetch('/status');
                const data = await response.json();
                renderStatus(data);
            }

            function renderStatus(data) {
                const nodes = data.nodes;
                const tasks = data.tasks;
                const latestMetrics = data.latest_metrics;
                const xai = data.xai;
                const forecast = data.forecast;
                const ml = latestMetrics ? latestMetrics.ml : null;
                const serverFile = data.server_file;
                const latestPresent = data.latest_result_present;
                const timeoutSeconds = data.node_timeout_seconds ?? 30;
                const graceSeconds = data.working_grace_seconds ?? 5;
                
                const html = `
                    <div class="grid">
                        <div class="card">
                            <h2> System Overview</h2>
                            <div class="stat">
                                <span class="stat-label">Total Nodes</span>
                                <span class="stat-value">${nodes.total}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Alive Nodes</span>
                                <span class="stat-value status-alive">${nodes.alive}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Working Nodes</span>
                                <span class="stat-value status-working">${nodes.working}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Dead Nodes</span>
                                <span class="stat-value status-dead">${nodes.dead}</span>
                            </div>
                        </div>

                        <div class="card">
                            <h2> Task Statistics</h2>
                            <div class="stat">
                                <span class="stat-label">Total Tasks</span>
                                <span class="stat-value">${tasks.total}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Pending</span>
                                <span class="stat-value status-pending">${tasks.pending}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Assigned</span>
                                <span class="stat-value status-working">${tasks.assigned}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Completed</span>
                                <span class="stat-value status-completed">${tasks.completed}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Failed</span>
                                <span class="stat-value status-failed">${tasks.failed}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Queue Size</span>
                                <span class="stat-value">${tasks.queue_size}</span>
                            </div>
                        </div>
                    </div>

                    <div class="grid">
                        <div class="card">
                            <h2> Latest Phone Calculations</h2>
                            ${latestMetrics ? `
                                <div class="stat">
                                    <span class="stat-label">Congestion</span>
                                    <span class="stat-value">${latestMetrics.congestion_level?.toUpperCase?.() || latestMetrics.congestion_level} (${latestMetrics.congestion_score}/10)</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Movements</span>
                                    <span class="stat-value">${latestMetrics.total_movements} (A ${latestMetrics.arrivals} / D ${latestMetrics.departures})</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Density</span>
                                    <span class="stat-value">${latestMetrics.traffic_density} /hr</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Occupancy</span>
                                    <span class="stat-value">${latestMetrics.runway_occupancy_percent}%</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Spacing (avg / min)</span>
                                    <span class="stat-value">${latestMetrics.avg_spacing_minutes}m / ${latestMetrics.min_spacing_minutes}m</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Peak Hour</span>
                                    <span class="stat-value">${String(latestMetrics.peak_hour).padStart(2,'0')}:00 (${latestMetrics.peak_hour_movements})</span>
                                </div>
                                <div class="timestamp">
                                    Computed at: ${latestMetrics.computed_at}
                                </div>
                            ` : `
                                <div style="color: #94a3b8;">No completed phone results yet.</div>
                            `}
                        </div>
                        <div class="card">
                            <h2> XAI: Why This Result</h2>
                            ${xai ? `
                                <div class="stat">
                                    <span class="stat-label">Level / Score</span>
                                    <span class="stat-value">${xai.congestion_level?.toUpperCase?.() || xai.congestion_level} (${xai.congestion_score}/10)</span>
                                </div>
                                ${xai.reasons.map(r => `
                                    <div class="stat">
                                        <span class="stat-label">Reason</span>
                                        <span class="stat-value">${r}</span>
                                    </div>
                                `).join('')}
                                <div class="timestamp" style="margin-top: 8px;">
                                    Signals: density ${xai.signals.traffic_density_per_hr}/hr, occupancy ${xai.signals.runway_occupancy_percent}%, min spacing ${xai.signals.min_spacing_minutes}m
                                </div>
                            ` : `
                                <div style="color: #94a3b8;">XAI not available yet.</div>
                            `}
                        </div>
                        <div class="card">
                            <h2> ML Findings</h2>
                            ${ml ? `
                                <div class="stat">
                                    <span class="stat-label">Method</span>
                                    <span class="stat-value">${ml.method} (${ml.samples} samples, ${ml.bin_minutes}m bins)</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Predicted Congestion</span>
                                    <span class="stat-value">${ml.predicted_congestion_level?.toUpperCase?.() || ml.predicted_congestion_level}</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Predicted Density</span>
                                    <span class="stat-value">${ml.predicted_traffic_density_per_hr} /hr</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Predicted Occupancy</span>
                                    <span class="stat-value">${ml.predicted_runway_occupancy_percent}%</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Trend (density/bin)</span>
                                    <span class="stat-value">${ml.trend_density_per_bin}</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Trend (occupancy/bin)</span>
                                    <span class="stat-value">${ml.trend_occupancy_percent_per_bin}%</span>
                                </div>
                            ` : `
                                <div style="color: #94a3b8;">ML findings not available yet.</div>
                            `}
                        </div>
                        <div class="card">
                            <h2> Forecast: Next Window</h2>
                            ${forecast ? `
                                <div class="stat">
                                    <span class="stat-label">Method</span>
                                    <span class="stat-value">${forecast.method} (last ${forecast.window_points})</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Congestion</span>
                                    <span class="stat-value">${forecast.predicted_congestion_level?.toUpperCase?.() || forecast.predicted_congestion_level} (${forecast.predicted_congestion_score})</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Density</span>
                                    <span class="stat-value">${forecast.predicted_traffic_density_per_hr} /hr</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Occupancy</span>
                                    <span class="stat-value">${forecast.predicted_runway_occupancy_percent}%</span>
                                </div>
                                <div class="stat">
                                    <span class="stat-label">Arrivals / Departures</span>
                                    <span class="stat-value">${forecast.predicted_arrivals} / ${forecast.predicted_departures}</span>
                                </div>
                            ` : `
                                <div style="color: #94a3b8;">Forecast not available yet.</div>
                            `}
                        </div>
                    </div>

                    <div class="grid">
                        <div class="card">
                            <h2> Active Nodes</h2>
                            ${nodes.details.map(node => {
                                const derivedStatus = (node.seconds_since_heartbeat > timeoutSeconds)
                                    ? 'dead'
                                    : (node.current_task || (node.seconds_since_activity <= graceSeconds))
                                        ? 'working'
                                        : 'idle';
                                return `
                                <div class="node-item">
                                    <div>
                                        <strong>${node.node_id}</strong>
                                        <span class="status-${derivedStatus}">  ${derivedStatus.toUpperCase()}</span>
                                    </div>
                                    <div class="timestamp">
                                        Last heartbeat: ${Math.round(node.seconds_since_heartbeat)}s ago | Last activity: ${Math.round(node.seconds_since_activity)}s ago
                                    </div>
                                    <div style="margin-top: 8px;">
                                        <span style="color: #64748b;">Tasks:</span>
                                        <span style="color: #10b981;">${node.tasks_completed}</span>
                                        <span style="color: #ef4444;">${node.tasks_failed}</span>
                                        ${node.current_task ? `<span style="color: #3b82f6;"> ${node.current_task}</span>` : ''}
                                    </div>
                                </div>
                            `}).join('')}
                        </div>

                        <div class="card">
                            <h2> Recent Tasks</h2>
                            ${tasks.recent_tasks.slice(0, 10).map(task => `
                                <div class="task-item">
                                    <div>
                                        <strong>${task.task_id}</strong>
                                        <span class="status-${task.status}"> ${task.status.toUpperCase()}</span>
                                    </div>
                                    <div style="margin-top: 5px; color: #94a3b8;">
                                        Type: ${task.type} | Window: ${task.window_minutes}m
                                    </div>
                                    <div style="margin-top: 5px; color: #94a3b8;">
                                        Node: ${task.node_id || 'unassigned'}
                                        ${task.duration_seconds ? ` | Duration: ${task.duration_seconds.toFixed(1)}s` : ''}
                                    </div>
                                    ${task.task_data_summary && task.task_data_summary.traffic_movements !== null ? `
                                        <div style="margin-top: 5px; color: #94a3b8;">
                                            Data: ${task.task_data_summary.traffic_movements} movements | ${task.task_data_summary.airport_code || 'N/A'} ${task.task_data_summary.runway || ''}
                                        </div>
                                    ` : ''}
                                    ${task.result_summary && task.result_summary.congestion_level ? `
                                        <div style="margin-top: 5px; color: #94a3b8;">
                                            Result: ${task.result_summary.congestion_level.toUpperCase()} (${task.result_summary.congestion_score}/10), Density ${task.result_summary.traffic_density}/hr, Occupancy ${task.result_summary.runway_occupancy_percent}%
                                        </div>
                                    ` : ''}
                                    <div class="timestamp">
                                        Created: ${new Date(task.created_at).toLocaleTimeString()}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
                
                document.getElementById('content').innerHTML = html;
            }

            // Initial fetch
            fetchStatus();
            
            // Auto-refresh every 2 seconds
            setInterval(fetchStatus, 2000);
        </script>
    </body>
    </html>
    """)


@app.get("/status")
def get_status() -> Dict[str, Any]:
    """Get detailed system status"""
    return task_manager.get_status()


@app.get("/summary")
def get_summary() -> Dict[str, Any]:
    """Get congestion summary"""
    summary = store.get()
    if summary is None:
        raise HTTPException(status_code=503, detail="Summary not ready")
    return summary


@app.post("/node/heartbeat")
def node_heartbeat(payload: dict):
    """Register node heartbeat"""
    node_id = payload.get("node")
    if not node_id:
        raise HTTPException(status_code=400, detail="Missing node ID")
    
    task_manager.register_node(node_id)
    return JSONResponse({"status": "ok", "timestamp": time.time()})


@app.get("/task")
def get_task(node_id: str = Query(...)) -> Optional[Dict[str, Any]]:
    """Get next task for a node"""
    task_manager.register_node(node_id)  # Also counts as heartbeat
    task = task_manager.get_next_task(node_id)
    return task


@app.post("/task-result")
def task_result(result: Dict[str, Any]):
    """Receive task result from node"""
    task_id = result.get("task_id")
    node_id = result.get("node_id")
    logger.info(
        " Task result received: task_id=%s node_id=%s status=%s keys=%s",
        task_id,
        node_id,
        result.get("status"),
        list(result.keys()),
    )
    
    if not task_id or not node_id:
        raise HTTPException(status_code=400, detail="Missing task_id or node_id")
    
    if result.get("status") == "completed":
        task_manager.complete_task(task_id, node_id, result)
    else:
        error = result.get("error", "Unknown error")
        task_manager.fail_task(task_id, node_id, error)
    
    return {"status": "ok"}


@app.post("/edge-feedback")
def edge_feedback(payload: EdgeFeedback) -> Dict[str, Any]:
    """Log decisions from edge node"""
    logger.info(
        "Edge decision received: decision=%s notes=%s timestamp=%s",
        payload.decision,
        payload.notes,
        payload.timestamp_utc,
    )
    return {"status": "ok"}


# -----------------------------
# Local dev entrypoint
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
