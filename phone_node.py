import requests
import socket
import time

EDGE_URL = "http://10.39.86.168:8000"  # Mac IP
NODE_ID = "phone-node-1"

while True:
    timestamp = time.time()
    # Heartbeat
    try:
        r = requests.post(f"{EDGE_URL}/node/heartbeat", json={
            "node": NODE_ID,
            "status": "alive",
            "timestamp": timestamp
        })
        print(f"[{timestamp}] Heartbeat sent, status: {r.status_code}")
    except Exception as e:
        print("Heartbeat error:", e)

    # Fetch task
    try:
        r = requests.get(f"{EDGE_URL}/task", params={"node_id": NODE_ID})
        task = r.json().get("task")
        print(f"[{timestamp}] Received task: {task}")
    except Exception as e:
        print("Task fetch error:", e)
        task = None

    # Process task
    if task:
        if task["type"] == "process_departures":
            data = task["data"]
            total = len(data)
            departure_rate = total / 1  # simplistic
            result = {
                "departure_rate": departure_rate,
                "traffic_density": total,
                "estimated_runway_occupancy": total*0.05
            }
            print(f"[{timestamp}] Processed task result: {result}")
            try:
                r = requests.post(f"{EDGE_URL}/task-result", json=result, params={"node_id": NODE_ID})
                print(f"[{timestamp}] Sent result, status: {r.status_code}")
            except Exception as e:
                print("Result post error:", e)

    time.sleep(10)
