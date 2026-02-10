import requests
import time
import socket

MAC_NODE = "http://172.17.97.42:8000"

NODE_ID = socket.gethostname()

while True:
    payload = {
        "node": NODE_ID,
        "status": "alive",
        "timestamp": time.time()
    }

    try:
        r = requests.post(f"{MAC_NODE}/node/heartbeat", json=payload)
        print("Sent heartbeat:", r.status_code)
    except Exception as e:
        print("Error:", e)

    time.sleep(10)
