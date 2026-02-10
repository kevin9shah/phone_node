import requests
import time
import socket

EDGE_URL = "http://10.39.86.168:8000"   # MacBook IP

NODE_ID = socket.gethostname()

while True:
    payload = {
        "node": NODE_ID,
        "status": "alive",
        "timestamp": time.time()
    }

    try:
        r = requests.post(f"{EDGE_URL}/node/heartbeat", json=payload)
        print("Sent heartbeat:", r.status_code)
    except Exception as e:
        print("Error:", e)

    time.sleep(10)
