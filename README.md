# VABB Distributed Task System

A local distributed task system for runway congestion analysis with a FastAPI server, a phone-based worker, and a live dashboard.

## Folder Map

- `app.py` Server and task manager (FastAPI + background task engine)
- `phone_node.py` Worker that fetches tasks and performs real calculations
- `sample_runway_data.csv` Sample/generated runway traffic data
- `edge_feedback.log` Server log output
- `Quickstart.md` Original quickstart guide (may reference older filenames)
- `realcalculations.md` Detailed description of the worker calculations
- `improvements.md` Notes on transparency/monitoring enhancements
- `venv` Local virtual environment (optional)

## How It Works

- The server (`app.py`) runs a background `CongestionEngine`.
- Every cycle, it loads or generates runway traffic rows and creates tasks with real traffic data.
- Workers (`phone_node.py`) poll for tasks, compute metrics, and POST results back.
- The dashboard shows live status at `http://YOUR_MAC_IP:8000/dashboard`.

## Exact Calculations Performed by `phone_node.py`

The worker runs these calculations in `process_task()` when `task_type == "compute_congestion"`:

1. Movement counts
Arrivals, departures, total movements.

2. Traffic density and rates
- `traffic_density = total_movements / (window_minutes / 60)`
- `arrival_rate = arrivals / (window_minutes / 60)`
- `departure_rate = departures / (window_minutes / 60)`

3. Runway occupancy percentage
- `runway_occupancy = total_occupancy_seconds / (window_minutes * 60)`
- Capped at 100%.

4. Peak hour detection
Counts movements by hour from `timestamp_utc` and selects the max.

5. Spacing analysis
- Sorts movements by `timestamp_utc`
- Computes gaps between consecutive movements in minutes
- Outputs `avg_spacing_minutes` and `min_spacing_minutes`

6. Congestion classification and score
- High if `traffic_density > 30` or `runway_occupancy > 0.7`
- Medium if `traffic_density > 15` or `runway_occupancy > 0.4`
- Low otherwise
- Adds a +2 score penalty if `min_spacing_minutes < 3.0`

7. Movement distribution and imbalance
- `arrival_percentage`, `departure_percentage`
- Logs imbalance if arrivals are >30% away from 50/50

8. Average occupancy by movement type
- Average occupancy seconds for arrivals and departures separately

The worker returns a result payload that includes all metrics above, plus:
- `processing_time_seconds`
- `window_minutes`
- `airport_code` and `runway`
- `computed_at` timestamp

## Task Generation and Data Window

- The server creates tasks from rows that fall within the last `WINDOW_MINUTES`.
- If there is no data in the current window, it regenerates the CSV and skips task creation if still empty.

## Configuration

Server (`app.py`):

- `WINDOW_MINUTES = 60`
- `CYCLE_SECONDS = 45`
- `TASKS_PER_CYCLE = 5`
- `NODE_TIMEOUT_SECONDS = 30`
- `TASK_TIMEOUT_SECONDS = 60`

Worker (`phone_node.py`):

- `HEARTBEAT_INTERVAL = 5`
- `TASK_POLL_INTERVAL = 3`
- `MAX_RETRIES = 3`
- `TIMEOUT = 5`

## Running

Server:

```bash
pip install fastapi uvicorn requests pydantic
python app.py
```

Worker (phone):

```python
# Update this in phone_node.py
SERVER_URL = "http://YOUR_MAC_IP:8000"
```

```bash
python phone_node.py
```

## API Endpoints

- `GET /dashboard` Live dashboard
- `GET /status` Node/task stats
- `GET /summary` Congestion summary
- `POST /node/heartbeat` Worker heartbeat
- `GET /task?node_id=<id>` Fetch task
- `POST /task-result` Submit task result

## Notes

- `Quickstart.md` references older filenames (`app_enhanced.py`, `phone_node_enhanced.py`). The actual entrypoints in this folder are `app.py` and `phone_node.py`.
- If you open a `realcalculations.d` tab, there is no such file in this folder.
