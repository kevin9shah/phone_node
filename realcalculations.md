# Real Calculations, ML, and XAI (Exact Formulas)

This document is the authoritative reference for all calculations, ML forecasting, and XAI logic used in this project.

## Definitions

- `window_minutes`: time window for analysis (default 60).
- `window_hours = window_minutes / 60.0`.
- `window_seconds = window_minutes * 60.0`.
- `traffic_movements`: list of movements, each with:
  - `timestamp_utc` (ISO 8601)
  - `movement_type` in {`arrival`, `departure`}
  - `occupancy_seconds`

All calculations below are performed by the phone worker in `phone_node.py`.

## Core Metrics (Per Task)

### 1) Movement Counts
- `arrivals = count(movement_type == "arrival")`
- `departures = count(movement_type == "departure")`
- `total_movements = arrivals + departures`

### 2) Traffic Density and Rates
- `traffic_density = total_movements / window_hours`
- `arrival_rate = arrivals / window_hours`
- `departure_rate = departures / window_hours`

### 3) Runway Occupancy Percentage
- `total_occupancy_seconds = sum(occupancy_seconds)`
- `runway_occupancy = total_occupancy_seconds / window_seconds`
- `runway_occupancy = min(1.0, runway_occupancy)`
- `runway_occupancy_percent = runway_occupancy * 100`

### 4) Peak Hour Detection
- Extract hour from each `timestamp_utc`.
- Count movements per hour.
- `peak_hour = argmax(hourly_counts)`
- `peak_hour_movements = max(hourly_counts)`

### 5) Spacing Analysis
- Sort movements by `timestamp_utc`.
- For each adjacent pair:
  - `gap_minutes = (t2 - t1).total_seconds() / 60.0`
- `avg_spacing_minutes = mean(gap_minutes)`
- `min_spacing_minutes = min(gap_minutes)`

### 6) Congestion Level and Score
Classification rules:

- High if `traffic_density > 30` OR `runway_occupancy > 0.7`
- Medium if `traffic_density > 15` OR `runway_occupancy > 0.4`
- Low otherwise

Score:
- Base score: 9 (high), 5 (medium), 2 (low)
- If `min_spacing_minutes < 3.0` and `min_spacing_minutes > 0`, add +2

### 7) Arrival/Departure Balance
- `arrival_percentage = arrivals / total_movements * 100`
- `departure_percentage = departures / total_movements * 100`
- `imbalance = abs(arrival_percentage - 50.0)`
- If `imbalance > 30`, flag imbalance

### 8) Average Occupancy by Movement Type
- `arrival_occupancy = sum(occupancy_seconds for arrivals)`
- `departure_occupancy = sum(occupancy_seconds for departures)`
- `avg_arrival_occupancy_seconds = arrival_occupancy / arrivals`
- `avg_departure_occupancy_seconds = departure_occupancy / departures`

## ML Forecast (Phone Worker)

The phone runs a simple linear regression forecast on binned traffic data.

### Binning
- `bin_minutes = 5`
- `bin_seconds = bin_minutes * 60`
- `bins = floor((window_end - window_start) / bin_seconds) + 1`

For each bin `i`:
- `counts[i]` = number of movements in bin `i`
- `occ_sums[i]` = sum of occupancy seconds in bin `i`

### Derived Series
- `density_series[i] = counts[i] * (60 / bin_minutes)`
- `occupancy_series[i] = min(100, (occ_sums[i] / bin_seconds) * 100)`

### Linear Regression
For `x = 0..bins-1`:

- `x_mean = mean(x)`
- `y_mean = mean(y)`
- `slope = sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean)^2)`
- `intercept = y_mean - slope * x_mean`

Prediction:
- `next_x = bins`
- `pred_density = max(0, slope_d * next_x + intercept_d)`
- `pred_occupancy = clamp(0, 100, slope_o * next_x + intercept_o)`

Predicted congestion level (same thresholds as core):
- High if `pred_density > 30` OR `pred_occupancy > 70`
- Medium if `pred_density > 15` OR `pred_occupancy > 40`
- Low otherwise

Returned ML fields (`result.ml`):
- `method = "linear_regression"`
- `bin_minutes = 5`
- `samples = bins`
- `predicted_traffic_density_per_hr`
- `predicted_runway_occupancy_percent`
- `predicted_congestion_level`
- `trend_density_per_bin = slope_d`
- `trend_occupancy_percent_per_bin = slope_o`

## XAI (Explainability)

XAI is computed server-side from the latest completed metrics.

### Signals
- `traffic_density_per_hr`
- `runway_occupancy_percent`
- `min_spacing_minutes`
- `arrival_departure_imbalance_pct` (if available)

### Reasoning Rules
- Density:
  - `> 30/hr` -> "High traffic density (>30/hr)"
  - `15-30/hr` -> "Moderate traffic density (15-30/hr)"
  - `<= 15/hr` -> "Low traffic density (<=15/hr)"

- Occupancy:
  - `> 70%` -> "High runway occupancy (>70%)"
  - `40-70%` -> "Moderate runway occupancy (40-70%)"
  - `<= 40%` -> "Low runway occupancy (<=40%)"

- Spacing:
  - `< 3 min` -> "Tight spacing (<3 min) increases score"
  - `>= 3 min` -> "Spacing acceptable (>=3 min)"

- Imbalance:
  - `> 30%` -> "High arrival/departure imbalance (>30%)"

### XAI Output
- `congestion_level`
- `congestion_score`
- `reasons[]`
- `signals{...}`
- `thresholds{...}`

## Output Schema (Phone -> Server)

Each completed task returns:

```json
{
  "task_id": "task-00001",
  "node_id": "phone-node-1",
  "status": "completed",
  "task_type": "compute_congestion",
  "result": {
    "congestion_level": "low",
    "congestion_score": 2,
    "total_movements": 7,
    "arrivals": 3,
    "departures": 4,
    "arrival_percentage": 42.9,
    "departure_percentage": 57.1,
    "traffic_density": 7.0,
    "arrival_rate": 3.0,
    "departure_rate": 4.0,
    "runway_occupancy_percent": 15.7,
    "total_occupancy_seconds": 660,
    "avg_arrival_occupancy_seconds": 74.0,
    "avg_departure_occupancy_seconds": 86.0,
    "avg_spacing_minutes": 5.0,
    "min_spacing_minutes": 5.0,
    "peak_hour": 9,
    "peak_hour_movements": 4,
    "window_minutes": 60,
    "computed_at": "2026-02-10T16:11:40",
    "airport_code": "VABB",
    "runway": "09/27",
    "ml": {
      "method": "linear_regression",
      "bin_minutes": 5,
      "samples": 7,
      "predicted_traffic_density_per_hr": 6.8,
      "predicted_runway_occupancy_percent": 15.2,
      "predicted_congestion_level": "low",
      "trend_density_per_bin": -0.1,
      "trend_occupancy_percent_per_bin": -0.3,
      "window_minutes": 60
    }
  },
  "processing_time_seconds": 0.003,
  "timestamp": 1770711100.0
}
```
