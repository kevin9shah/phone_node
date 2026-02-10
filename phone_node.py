"""
Enhanced phone node with transparent task distribution
- Clear logging of all operations
- Task status tracking
- Performance metrics
- Better error handling
"""

import requests
import time
import json
from datetime import datetime
from typing import Optional, Dict, Any

# Configuration
SERVER_URL = "http://10.39.86.168:8000"  # Replace with your Mac's LAN IP
NODE_ID = "phone-node-1"
HEARTBEAT_INTERVAL = 5  # seconds
TASK_POLL_INTERVAL = 3  # seconds
MAX_RETRIES = 3
TIMEOUT = 5

# Statistics tracking
class NodeStats:
    def __init__(self):
        self.tasks_fetched = 0
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.heartbeats_sent = 0
        self.heartbeat_failures = 0
        self.start_time = time.time()
        self.total_task_time = 0.0
    
    def print_stats(self):
        uptime = time.time() - self.start_time
        print("\n" + "="*60)
        print(f"📊 NODE STATISTICS ({NODE_ID})")
        print("="*60)
        print(f"⏱️  Uptime: {uptime:.0f}s ({uptime/60:.1f} minutes)")
        print(f"💓 Heartbeats: {self.heartbeats_sent} sent, {self.heartbeat_failures} failed")
        print(f"📋 Tasks: {self.tasks_fetched} fetched, {self.tasks_completed} completed, {self.tasks_failed} failed")
        if self.tasks_completed > 0:
            avg_time = self.total_task_time / self.tasks_completed
            print(f"⚡ Average task time: {avg_time:.2f}s")
        print("="*60 + "\n")

stats = NodeStats()


def log(emoji: str, message: str, level: str = "INFO"):
    """Formatted logging with timestamps"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {emoji} {message}")
    

def make_request(method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
    """Make HTTP request with retry logic"""
    url = f"{SERVER_URL}{endpoint}"
    
    for attempt in range(MAX_RETRIES):
        try:
            if method == "GET":
                response = requests.get(url, timeout=TIMEOUT, **kwargs)
            elif method == "POST":
                response = requests.post(url, timeout=TIMEOUT, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.Timeout:
            log("⏰", f"Request timeout (attempt {attempt + 1}/{MAX_RETRIES})", "WARN")
        except requests.exceptions.ConnectionError:
            log("🔌", f"Connection error (attempt {attempt + 1}/{MAX_RETRIES})", "WARN")
        except requests.exceptions.HTTPError as e:
            log("❌", f"HTTP error: {e.response.status_code}", "ERROR")
            return None
        except Exception as e:
            log("💥", f"Unexpected error: {str(e)}", "ERROR")
            return None
        
        if attempt < MAX_RETRIES - 1:
            time.sleep(1)  # Wait before retry
    
    return None


def send_heartbeat() -> bool:
    """Send heartbeat to server"""
    payload = {
        "node": NODE_ID,
        "status": "alive",
        "timestamp": time.time()
    }
    
    response = make_request("POST", "/node/heartbeat", json=payload)
    
    if response:
        stats.heartbeats_sent += 1
        log("💓", f"Heartbeat sent successfully", "DEBUG")
        return True
    else:
        stats.heartbeat_failures += 1
        log("💔", "Heartbeat failed", "WARN")
        return False


def fetch_task() -> Optional[Dict[str, Any]]:
    """Fetch next task from server"""
    log("🔍", "Polling for new task...")
    
    response = make_request("GET", "/task", params={"node_id": NODE_ID})
    
    if not response:
        log("❌", "Failed to fetch task", "ERROR")
        return None
    
    try:
        task = response.json()
        if task:
            stats.tasks_fetched += 1
            log("📥", f"Received task: {task.get('task_id')} (type: {task.get('type')})", "INFO")
            log("  ", f"└─ Assigned at: {task.get('assigned_at')}")
            return task
        else:
            log("📭", "No tasks available in queue", "DEBUG")
            return None
    except json.JSONDecodeError:
        log("💥", "Invalid JSON response", "ERROR")
        return None


def send_task_result(result: Dict[str, Any]) -> bool:
    """Send task result to server"""
    task_id = result.get('task_id')
    status = result.get('status')
    
    log("📤", f"Sending result for {task_id} (status: {status})")
    
    response = make_request("POST", "/task-result", json=result)
    
    if response:
        try:
            log("📬", f"Server response: {response.status_code} {response.text.strip()}", "DEBUG")
        except Exception:
            pass
        if status == "completed":
            stats.tasks_completed += 1
            log("✅", f"Task {task_id} result sent successfully", "INFO")
        else:
            stats.tasks_failed += 1
            log("❌", f"Task {task_id} marked as failed", "WARN")
        return True
    else:
        log("📛", f"Failed to send result for {task_id}", "ERROR")
        return False


def process_task(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process task and return result - NOW WITH REAL CALCULATIONS!"""
    if not task:
        return None
    
    task_id = task.get('task_id')
    task_type = task.get('type')
    
    log("⚙️", f"Processing task {task_id}...", "INFO")
    start_time = time.time()
    
    try:
        if task_type == "compute_congestion":
            # Extract real traffic data from task
            data = task.get('data', {})
            traffic_movements = data.get('traffic_movements', [])
            window_minutes = task.get('window_minutes', 60)
            
            log("  ", f"└─ Analyzing {len(traffic_movements)} traffic movements...")
            
            if not traffic_movements:
                log("⚠️", "No traffic data to analyze", "WARN")
                return {
                    "task_id": task_id,
                    "node_id": NODE_ID,
                    "status": "failed",
                    "error": "No traffic data provided",
                    "timestamp": time.time()
                }
            
            # REAL CALCULATION 1: Count movements by type
            arrivals = sum(1 for m in traffic_movements if m['movement_type'] == 'arrival')
            departures = sum(1 for m in traffic_movements if m['movement_type'] == 'departure')
            total_movements = arrivals + departures
            
            log("  ", f"└─ Found {arrivals} arrivals, {departures} departures")
            
            # REAL CALCULATION 2: Traffic density (movements per hour)
            window_hours = window_minutes / 60.0
            traffic_density = total_movements / window_hours if window_hours > 0 else 0.0
            arrival_rate = arrivals / window_hours if window_hours > 0 else 0.0
            departure_rate = departures / window_hours if window_hours > 0 else 0.0
            
            log("  ", f"└─ Traffic density: {traffic_density:.1f} movements/hour")
            
            # REAL CALCULATION 3: Runway occupancy percentage
            total_occupancy_seconds = sum(m['occupancy_seconds'] for m in traffic_movements)
            window_seconds = window_minutes * 60.0
            runway_occupancy = total_occupancy_seconds / window_seconds if window_seconds > 0 else 0.0
            runway_occupancy = min(1.0, runway_occupancy)  # Cap at 100%
            
            log("  ", f"└─ Runway occupancy: {runway_occupancy*100:.1f}%")
            
            # REAL CALCULATION 4: Peak hour detection
            # Group movements by hour and find peak
            from collections import defaultdict
            hourly_counts = defaultdict(int)
            for movement in traffic_movements:
                # Parse timestamp and extract hour
                ts_str = movement['timestamp_utc']
                hour = int(ts_str[11:13])  # Extract hour from ISO format
                hourly_counts[hour] += 1
            
            peak_hour = max(hourly_counts.items(), key=lambda x: x[1]) if hourly_counts else (0, 0)
            log("  ", f"└─ Peak hour: {peak_hour[0]:02d}:00 with {peak_hour[1]} movements")
            
            # REAL CALCULATION 5: Average spacing between movements
            if len(traffic_movements) > 1:
                # Sort by timestamp
                sorted_movements = sorted(traffic_movements, key=lambda x: x['timestamp_utc'])
                
                # Calculate time gaps in minutes
                gaps = []
                for i in range(len(sorted_movements) - 1):
                    t1 = datetime.fromisoformat(sorted_movements[i]['timestamp_utc'])
                    t2 = datetime.fromisoformat(sorted_movements[i+1]['timestamp_utc'])
                    gap_minutes = (t2 - t1).total_seconds() / 60.0
                    gaps.append(gap_minutes)
                
                avg_spacing = sum(gaps) / len(gaps) if gaps else 0.0
                min_spacing = min(gaps) if gaps else 0.0
                
                log("  ", f"└─ Avg spacing: {avg_spacing:.1f} min, Min: {min_spacing:.1f} min")
            else:
                avg_spacing = 0.0
                min_spacing = 0.0
            
            # REAL CALCULATION 6: Congestion classification
            if traffic_density > 30 or runway_occupancy > 0.7:
                congestion_level = "high"
                congestion_score = 9
            elif traffic_density > 15 or runway_occupancy > 0.4:
                congestion_level = "medium"
                congestion_score = 5
            else:
                congestion_level = "low"
                congestion_score = 2
            
            # Add penalty for tight spacing
            if min_spacing < 3.0 and min_spacing > 0:
                congestion_score += 2
                log("  ", f"└─ ⚠️ Tight spacing detected! Added penalty to score")
            
            log("  ", f"└─ Congestion: {congestion_level.upper()} (score: {congestion_score}/10)")
            
            # REAL CALCULATION 7: Movement distribution analysis
            arrival_percentage = (arrivals / total_movements * 100) if total_movements > 0 else 0
            departure_percentage = (departures / total_movements * 100) if total_movements > 0 else 0
            
            # Check for imbalance (runway might be stressed if too many arrivals or departures)
            imbalance = abs(arrival_percentage - 50.0)
            if imbalance > 30:
                log("  ", f"└─ ⚠️ High imbalance: {arrival_percentage:.0f}% arrivals")
            
            # REAL CALCULATION 8: Occupancy rate by movement type
            arrival_occupancy = sum(m['occupancy_seconds'] for m in traffic_movements if m['movement_type'] == 'arrival')
            departure_occupancy = sum(m['occupancy_seconds'] for m in traffic_movements if m['movement_type'] == 'departure')
            
            avg_arrival_time = arrival_occupancy / arrivals if arrivals > 0 else 0
            avg_departure_time = departure_occupancy / departures if departures > 0 else 0
            
            log("  ", f"└─ Avg times: Arrivals {avg_arrival_time:.0f}s, Departures {avg_departure_time:.0f}s")
            
            # Build comprehensive result
            result = {
                "task_id": task_id,
                "node_id": NODE_ID,
                "status": "completed",
                "task_type": task_type,
                "result": {
                    # Summary metrics
                    "congestion_level": congestion_level,
                    "congestion_score": congestion_score,
                    
                    # Traffic counts
                    "total_movements": total_movements,
                    "arrivals": arrivals,
                    "departures": departures,
                    "arrival_percentage": round(arrival_percentage, 1),
                    "departure_percentage": round(departure_percentage, 1),
                    
                    # Density metrics
                    "traffic_density": round(traffic_density, 2),
                    "arrival_rate": round(arrival_rate, 2),
                    "departure_rate": round(departure_rate, 2),
                    
                    # Occupancy metrics
                    "runway_occupancy_percent": round(runway_occupancy * 100, 1),
                    "total_occupancy_seconds": total_occupancy_seconds,
                    "avg_arrival_occupancy_seconds": round(avg_arrival_time, 1),
                    "avg_departure_occupancy_seconds": round(avg_departure_time, 1),
                    
                    # Spacing analysis
                    "avg_spacing_minutes": round(avg_spacing, 2),
                    "min_spacing_minutes": round(min_spacing, 2),
                    
                    # Peak analysis
                    "peak_hour": peak_hour[0],
                    "peak_hour_movements": peak_hour[1],
                    
                    # Metadata
                    "window_minutes": window_minutes,
                    "computed_at": datetime.now().isoformat(),
                    "airport_code": data.get('airport_code', 'UNKNOWN'),
                    "runway": data.get('runway', 'UNKNOWN')
                },
                "processing_time_seconds": 0.0,  # Will be filled below
                "timestamp": time.time()
            }
            
            log("✨", f"Completed {total_movements} movement analysis", "INFO")
            
        else:
            log("⚠️", f"Unknown task type: {task_type}", "WARN")
            result = {
                "task_id": task_id,
                "node_id": NODE_ID,
                "status": "failed",
                "error": f"Unknown task type: {task_type}",
                "timestamp": time.time()
            }
        
        processing_time = time.time() - start_time
        result["processing_time_seconds"] = round(processing_time, 3)
        stats.total_task_time += processing_time
        
        log("✨", f"Task {task_id} processed in {processing_time:.3f}s", "INFO")
        return result
        
    except Exception as e:
        processing_time = time.time() - start_time
        log("💥", f"Task {task_id} failed: {str(e)}", "ERROR")
        import traceback
        log("  ", f"└─ {traceback.format_exc()}", "ERROR")
        return {
            "task_id": task_id,
            "node_id": NODE_ID,
            "status": "failed",
            "error": str(e),
            "processing_time_seconds": round(processing_time, 3),
            "timestamp": time.time()
        }


def main_loop():
    """Main event loop"""
    log("🚀", f"Starting node {NODE_ID}", "INFO")
    log("🌐", f"Connecting to server: {SERVER_URL}", "INFO")
    
    last_heartbeat = 0
    last_stats = 0
    stats_interval = 30  # Print stats every 30 seconds
    
    # Initial heartbeat
    send_heartbeat()
    
    while True:
        try:
            current_time = time.time()
            
            # Send heartbeat periodically
            if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                send_heartbeat()
                last_heartbeat = current_time
            
            # Print stats periodically
            if current_time - last_stats >= stats_interval:
                stats.print_stats()
                last_stats = current_time
            
            # Fetch and process task
            task = fetch_task()
            
            if task:
                log("🎯", f"Starting work on {task.get('task_id')}", "INFO")
                
                # Process task
                result = process_task(task)
                
                if result:
                    # Send result
                    success = send_task_result(result)
                    
                    if success:
                        log("🎉", f"Task {task.get('task_id')} completed successfully!", "INFO")
                    else:
                        log("😞", f"Failed to report completion of {task.get('task_id')}", "ERROR")
                else:
                    log("⚠️", f"Task {task.get('task_id')} produced no result", "WARN")
            
            # Wait before next poll
            time.sleep(TASK_POLL_INTERVAL)
            
        except KeyboardInterrupt:
            log("👋", "Shutting down gracefully...", "INFO")
            stats.print_stats()
            break
        except Exception as e:
            log("💥", f"Unexpected error in main loop: {str(e)}", "ERROR")
            time.sleep(5)  # Wait a bit before continuing


if __name__ == "__main__":
    # Print startup banner
    print("\n" + "="*60)
    print("🤖 DISTRIBUTED EDGE NODE")
    print("="*60)
    print(f"Node ID: {NODE_ID}")
    print(f"Server: {SERVER_URL}")
    print(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    print(f"Task poll interval: {TASK_POLL_INTERVAL}s")
    print("="*60 + "\n")
    
    time.sleep(1)  # Pause for dramatic effect
    
    try:
        main_loop()
    except Exception as e:
        log("💀", f"Fatal error: {str(e)}", "CRITICAL")
        stats.print_stats()
