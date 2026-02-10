import requests
import socket
import time

EDGE_URL = "http://10.39.86.168:8000"  # Mac IP
NODE_ID = "phone-node-1"

while True:
    # Heartbeat
    requests.post(f"{EDGE_URL}/node/heartbeat", json={"node": NODE_ID, "status": "alive", "timestamp": time.time()})

    # Fetch task
    r = requests.get(f"{EDGE_URL}/task", params={"node_id": NODE_ID})
    task = r.json().get("task")
    if task:
        # Process departures only
        if task["type"] == "process_departures":
            data = task["data"]
            # Example: compute partial summary
            total = len(data)
            departure_rate = total / 1  # simplistic
            result = {"departure_rate": departure_rate, "traffic_density": total, "estimated_runway_occupancy": total*0.05}
            # Send result back
            requests.post(f"{EDGE_URL}/task-result", json=result, params={"node_id": NODE_ID})

    time.sleep(10)
