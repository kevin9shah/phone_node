import requests
import time

SERVER_URL = "http://<MAC_IP>:8000"  # replace with your Mac's LAN IP
NODE_ID = "phone-node-1"
HEARTBEAT_INTERVAL = 5  # seconds
TASK_INTERVAL = 10      # seconds

def send_heartbeat():
    payload = {"node": NODE_ID, "status": "alive"}
    try:
        r = requests.post(f"{SERVER_URL}/node/heartbeat", json=payload, timeout=5)
        return r.status_code
    except Exception as e:
        print("Heartbeat error:", e)
        return None

def fetch_task():
    try:
        r = requests.get(f"{SERVER_URL}/task", params={"node_id": NODE_ID}, timeout=5)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        print("Fetch task error:", e)
        return None

def send_task_result(result: dict):
    try:
        r = requests.post(f"{SERVER_URL}/task-result", json=result, timeout=5)
        return r.status_code
    except Exception as e:
        print("Send task result error:", e)
        return None

def process_task(task: dict):
    """Simulate doing work on the task."""
    if not task:
        return None
    if task["type"] == "compute_congestion":
        # Simple simulated result
        result = {
            "node_id": NODE_ID,
            "task_timestamp": task["timestamp"],
            "congestion_level": "medium",  # placeholder
            "computed_at": time.time(),
        }
        return result
    return None

def main_loop():
    while True:
        # Heartbeat
        status = send_heartbeat()
        print(f"[{time.time()}] Heartbeat sent, status:", status)

        # Fetch task
        task = fetch_task()
        print(f"[{time.time()}] Received task:", task)

        # Process and send result
        if task:
            result = process_task(task)
            if result:
                status = send_task_result(result)
                print(f"[{time.time()}] Sent result, status:", status)

        time.sleep(TASK_INTERVAL)

if __name__ == "__main__":
    main_loop()
