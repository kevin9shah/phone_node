import requests, socket, time

PRIMARY_NODE = "http://10.39.86.168:8000"  # MacBook IP
NODE_ID = socket.gethostname()

while True:
    # 1. Send heartbeat
    try:
        requests.post(f"{PRIMARY_NODE}/node/heartbeat", json={
            "node": NODE_ID,
            "status": "alive",
            "timestamp": time.time()
        })
    except:
        pass

    # 2. Fetch task
    try:
        resp = requests.get(f"{PRIMARY_NODE}/task").json()
        task_rows = resp.get("task", [])

        # 3. Process task
        # Example: compute traffic_density for subset
        arrivals = sum(1 for r in task_rows if r['movement_type']=='arrival')
        departures = sum(1 for r in task_rows if r['movement_type']=='departure')
        total = arrivals + departures
        metrics = {"arrivals": arrivals, "departures": departures, "total": total}

        # 4. Send results back
        requests.post(f"{PRIMARY_NODE}/task-result", json={
            "node": NODE_ID,
            "metrics": metrics
        })
    except:
        pass

    time.sleep(10)
