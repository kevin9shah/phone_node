"""
VABB primary node - FastAPI server
- Loads runway traffic data from CSV (or generates if stale/missing)
- Computes simple congestion metrics
- Exposes REST endpoints for summary and edge feedback
"""

from __future__ import annotations

import csv
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import requests

# -----------------------------
# Configuration
# -----------------------------
DATA_FILE = Path(__file__).with_name("sample_runway_data.csv")
WINDOW_MINUTES = 60
CYCLE_SECONDS = 45  # run every 30-60 seconds
AIRPORT_CODE = "VABB"
AIRPORT_IATA = "BOM"
RUNWAY = "09/27"
AVIATIONSTACK_ACCESS_KEY = os.getenv("AVIATIONSTACK_ACCESS_KEY")
AVIATIONSTACK_BASE_URL = "https://api.aviationstack.com/v1/flights"
# Free tiers can be tight; fetch less often and reuse cached API results
AVIATIONSTACK_MIN_FETCH_SECONDS = 300
DEFAULT_OCCUPANCY_SECONDS = 75

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
    movement_type: str  # arrival or departure
    runway: str
    occupancy_seconds: int


# -----------------------------
# Data Loading and Generation
# -----------------------------
class DataLoader:
    def __init__(self, path: Path):
        self.path = path

    def _parse_row(self, row: Dict[str, str]) -> TrafficRow:
        # Expecting ISO-8601 timestamp in UTC
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
                    # Skip malformed rows, keep it beginner-friendly
                    continue
        return rows


class DataGenerator:
    """Simple simulated data generator for runway movements."""

    def __init__(self, path: Path):
        self.path = path

    def generate(self, hours: int = 2, interval_minutes: int = 5) -> None:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)

        rows: List[TrafficRow] = []
        current = start
        while current <= now:
            # Randomly decide if a movement happened at this interval
            if random.random() < 0.75:  # 75% chance of a movement
                movement_type = "arrival" if random.random() < 0.5 else "departure"
                occupancy_seconds = random.randint(40, 120)
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
# Live Data (Aviationstack)
# -----------------------------
class AviationStackClient:
    """Minimal Aviationstack client for real-time flight data."""

    def __init__(self, access_key: str) -> None:
        self.access_key = access_key

    def _fetch(self, params: Dict[str, str]) -> List[Dict[str, Any]]:
        query = {"access_key": self.access_key}
        query.update(params)
        resp = requests.get(AVIATIONSTACK_BASE_URL, params=query, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("data", [])

    def get_recent_movements(
        self, now: datetime, window_minutes: int
    ) -> List[TrafficRow]:
        # Fetch departures and arrivals for the airport using ICAO code
        flight_date = now.date().isoformat()
        departures = self._fetch(
            {
                "dep_icao": AIRPORT_CODE,
                "flight_date": flight_date,
                "limit": "100",
            }
        )
        arrivals = self._fetch(
            {
                "arr_icao": AIRPORT_CODE,
                "flight_date": flight_date,
                "limit": "100",
            }
        )

        rows: List[TrafficRow] = []
        window_start = now - timedelta(minutes=window_minutes)

        def parse_time(record: Dict[str, Any], key: str) -> Optional[datetime]:
            data = record.get(key) or {}
            time_str = data.get("actual") or data.get("estimated") or data.get("scheduled")
            if not time_str:
                return None
            try:
                return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
            except Exception:
                return None

        for flight in departures:
            ts = parse_time(flight, "departure")
            if ts and ts >= window_start:
                rows.append(
                    TrafficRow(
                        timestamp_utc=ts,
                        movement_type="departure",
                        runway=RUNWAY,
                        occupancy_seconds=DEFAULT_OCCUPANCY_SECONDS,
                    )
                )

        for flight in arrivals:
            ts = parse_time(flight, "arrival")
            if ts and ts >= window_start:
                rows.append(
                    TrafficRow(
                        timestamp_utc=ts,
                        movement_type="arrival",
                        runway=RUNWAY,
                        occupancy_seconds=DEFAULT_OCCUPANCY_SECONDS,
                    )
                )

        return rows


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
        # Simple rules-based classification
        if density > 30 or occupancy > 0.7:
            return "high"
        if density > 15 or occupancy > 0.4:
            return "medium"
        return "low"


# -----------------------------
# Summary Store (thread-safe)
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
# Background Cycle
# -----------------------------
class CongestionEngine:
    def __init__(self, data_file: Path, store: SummaryStore):
        self.data_file = data_file
        self.store = store
        self.loader = DataLoader(data_file)
        self.generator = DataGenerator(data_file)
        self.calculator = MetricsCalculator()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_api_fetch: Optional[datetime] = None

        # Use live data if a key is present; otherwise fallback to CSV generation
        self._api_client: Optional[AviationStackClient] = None
        if AVIATIONSTACK_ACCESS_KEY:
            self._api_client = AviationStackClient(AVIATIONSTACK_ACCESS_KEY)

    def _ensure_recent_data(self) -> None:
        if self._api_client:
            # Live data mode: no CSV regeneration required
            return

        rows = self.loader.load()
        if not rows:
            self.generator.generate()
            return

        # If data is too old, regenerate to keep metrics meaningful
        now = datetime.now(timezone.utc)
        recent_rows = [r for r in rows if r.timestamp_utc >= now - timedelta(hours=24)]
        if not recent_rows:
            self.generator.generate()

    def _load_rows(self, now: datetime) -> List[TrafficRow]:
        if not self._api_client:
            return self.loader.load()

        # Throttle API calls to respect free tier limits
        if self._last_api_fetch and (
            now - self._last_api_fetch
        ).total_seconds() < AVIATIONSTACK_MIN_FETCH_SECONDS:
            # If we can't fetch yet, fall back to last CSV snapshot or empty
            return self.loader.load()

        rows = self._api_client.get_recent_movements(now, WINDOW_MINUTES)
        self._last_api_fetch = now

        # Cache to CSV for visibility/debugging
        with self.data_file.open("w", newline="") as f:
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

        return rows

    def _cycle(self) -> None:
        while not self._stop_event.is_set():
            self._ensure_recent_data()
            now = datetime.now(timezone.utc)
            rows = self._load_rows(now)
            summary = self.calculator.compute(rows, WINDOW_MINUTES, now)
            self.store.set(summary)
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
app = FastAPI(title="VABB Primary Node")
store = SummaryStore()
engine = CongestionEngine(DATA_FILE, store)


@app.on_event("startup")
def on_startup() -> None:
    # Run one cycle quickly so /summary has data at boot
    engine._ensure_recent_data()
    now = datetime.now(timezone.utc)
    rows = engine._load_rows(now)
    summary = engine.calculator.compute(rows, WINDOW_MINUTES, now)
    store.set(summary)
    engine.start()


@app.get("/summary")
def get_summary() -> Dict[str, Any]:
    summary = store.get()
    if summary is None:
        raise HTTPException(status_code=503, detail="Summary not ready")
    return summary


@app.post("/edge-feedback")
def edge_feedback(payload: EdgeFeedback) -> Dict[str, Any]:
    # Log decisions from edge node
    logger.info(
        "Edge decision received: decision=%s notes=%s timestamp=%s",
        payload.decision,
        payload.notes,
        payload.timestamp_utc,
    )
    return {"status": "ok"}

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import time
import socket

app = FastAPI(title="VABB Primary Node")

@app.post("/node/heartbeat")
def node_heartbeat(payload: dict):
    # Log heartbeat info
    print("Heartbeat received from node:", payload)
    return JSONResponse({"status": "ok", "timestamp": time.time()})


@app.get("/task")
def get_task(node_id: str):
    summary = store.get()
    if not summary:
        return {"task": None}

    # Split workload: phone handles departures, Mac handles arrivals
    if "phone" in node_id.lower():
        task = {
            "type": "process_departures",
            "data": summary.get("departures", []),
        }
    else:
        task = {
            "type": "process_arrivals",
            "data": summary.get("arrivals", []),
        }

    return {"task": task}


partial_results: Dict[str, Dict[str, Any]] = {}

@app.post("/task-result")
def task_result(node_id: str, payload: Dict[str, Any]):
    logger.info(f"Received task result from {node_id}: {payload}")
    partial_results[node_id] = payload

    # Combine all partial results to update summary
    combined_summary = {
        "traffic_density": 0,
        "arrival_rate": 0,
        "departure_rate": 0,
        "estimated_runway_occupancy": 0,
        "congestion_level": "low",
    }

    for r in partial_results.values():
        combined_summary["traffic_density"] += r.get("traffic_density", 0)
        combined_summary["arrival_rate"] += r.get("arrival_rate", 0)
        combined_summary["departure_rate"] += r.get("departure_rate", 0)
        combined_summary["estimated_runway_occupancy"] += r.get(
            "estimated_runway_occupancy", 0
        )
    # You can apply simple averaging
    n = len(partial_results)
    if n:
        for k in ["traffic_density", "arrival_rate", "departure_rate", "estimated_runway_occupancy"]:
            combined_summary[k] /= n

    # Optionally recalc congestion level
    if combined_summary["traffic_density"] > 30 or combined_summary["estimated_runway_occupancy"] > 0.7:
        combined_summary["congestion_level"] = "high"
    elif combined_summary["traffic_density"] > 15 or combined_summary["estimated_runway_occupancy"] > 0.4:
        combined_summary["congestion_level"] = "medium"
    else:
        combined_summary["congestion_level"] = "low"

    store.set(combined_summary)
    return {"status": "ok"}

# -----------------------------
# Local dev entrypoint
# -----------------------------
if __name__ == "__main__":
    # Run with: uvicorn app:app --host 0.0.0.0 --port 8000
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
