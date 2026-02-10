# VABB Distributed Task System

A local distributed task system for runway congestion analysis with a FastAPI server, a phone-based worker, and a live dashboard. The worker performs analytics and a simple ML forecast on each task.

## Contents

- Overview
- Architecture
- Data Flow
- What the Phone Computes
- ML Forecasting
- Task Details and Visibility
- Dashboard
- Configuration
- Running
- API
- Files
- Troubleshooting

## Overview

- Server: FastAPI app that generates tasks from `sample_runway_data.csv` and tracks nodes, tasks, and results.
- Phone worker: polls for tasks, computes congestion metrics, runs a lightweight ML forecast, and posts results back.
- Dashboard: live status with task details, XAI, and ML findings.

## Architecture

- `app.py`: Server, task manager, CSV data generation/loading, dashboard.
- `phone_node.py`: Edge worker that processes tasks and returns results.
- `sample_runway_data.csv`: Source data for tasks.

## Data Flow

1. Server loads CSV data (regenerates if stale).
2. Server creates tasks from the last `WINDOW_MINUTES` of data.
3. Phone polls and receives a task.
4. Phone computes metrics + ML forecast.
5. Phone posts results to `/task-result`.
6. Dashboard shows latest results, XAI reasoning, ML findings, and task summaries.

## What the Phone Computes

For each `compute_congestion` task, the phone computes:

1. Movement counts (arrivals, departures, total)
2. Rates (traffic density, arrival rate, departure rate)
3. Runway occupancy percentage
4. Peak hour (by timestamp)
5. Spacing (average and minimum gaps)
6. Congestion classification + score
7. Arrival/departure balance and imbalance check
8. Average occupancy by movement type

## ML Forecasting

The phone also runs a simple ML forecast per task:

- Bins movements into 5-minute intervals
- Fits a linear trend on density and occupancy
- Predicts next-window density, occupancy, and congestion level
- Returns the ML forecast under `result.ml`

## Task Details and Visibility

The dashboard shows per-task summaries:

- Task type, window size
- Data summary (movement count, airport, runway)
- Result summary (congestion level/score, density, occupancy)

This eliminates the black-box feel of tasks.

## Dashboard

Available at:

- `http://YOUR_MAC_IP:8000/dashboard`

Key sections:

- System overview (nodes/tasks)
- Latest phone calculations
- XAI explanation (why the congestion level)
- ML findings (forecast)
- Recent tasks with data/result summaries

## Configuration

Server (`app.py`):

- `WINDOW_MINUTES = 60`
- `CYCLE_SECONDS = 45`
- `TASKS_PER_CYCLE = 5`
- `NODE_TIMEOUT_SECONDS = 30`
- `TASK_TIMEOUT_SECONDS = 60`
- `WORKING_GRACE_SECONDS = 5`

Phone (`phone_node.py`):

- `SERVER_URL = "http://YOUR_MAC_IP:8000"`
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

Phone worker:

```bash
python phone_node.py
```

## API

- `GET /dashboard` Live dashboard
- `GET /status` Node/task stats and latest results
- `GET /summary` Congestion summary
- `POST /node/heartbeat` Worker heartbeat
- `GET /task?node_id=<id>` Fetch task
- `POST /task-result` Submit task result

## Files

- `app.py` Server + task manager + dashboard
- `phone_node.py` Worker + calculations + ML
- `sample_runway_data.csv` CSV data source
- `edge_feedback.log` Server log output
- `Quickstart.md` Older quickstart (may reference outdated filenames)
- `realcalculations.md` Detailed calculation notes
- `improvements.md` Notes about transparency improvements

## Troubleshooting

- No tasks: CSV data may be stale; the server regenerates it automatically.
- Phone shows IDLE: status uses a short working grace window; increase `WORKING_GRACE_SECONDS` if needed.
- Dashboard empty: ensure phone is posting to the same server IP shown in the dashboard.
