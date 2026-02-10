# VABB Distributed Task System - Transparent Edition

A transparent, monitored distributed computing system for runway congestion analysis with real-time visibility into task distribution between your Mac and phone.

## 🎯 Key Transparency Features

### 1. **Real-Time Dashboard** (`http://YOUR_MAC_IP:8000/dashboard`)
- Live system status updates every 2 seconds
- Visual node health monitoring
- Task queue and completion metrics
- Historical task tracking

### 2. **Comprehensive Logging**
- **Server side**: Detailed logs in `edge_feedback.log` with emoji indicators
- **Client side**: Color-coded console output with timestamps
- All task transitions tracked (created → assigned → completed/failed)

### 3. **Node Status Tracking**
- Heartbeat monitoring (nodes marked dead after 30s silence)
- Active task visualization
- Performance metrics per node
- Connection health indicators

### 4. **Task Lifecycle Visibility**
- **Pending**: Task created, waiting in queue
- **Assigned**: Task given to specific node
- **In Progress**: Node is working on it
- **Completed**: Successfully finished
- **Failed**: Error occurred
- **Timeout**: Node didn't complete in time (auto-requeued)

## 📊 What You Can Monitor

### System-Wide Metrics
- Total nodes (alive/dead/working/idle)
- Task statistics (total/pending/assigned/completed/failed)
- Queue size
- System uptime

### Per-Node Metrics
- Node ID and status
- Last heartbeat timestamp
- Tasks assigned/completed/failed
- Current task being processed
- Time since last contact

### Per-Task Metrics
- Task ID and type
- Creation time
- Assignment time
- Completion time
- Processing duration
- Assigned node
- Result data

## 🚀 Setup Instructions

### On Your Mac (Server)

1. **Install dependencies**:
```bash
pip install fastapi uvicorn requests pydantic
```

2. **Find your Mac's local IP address**:
```bash
# macOS
ipconfig getifaddr en0

# Or check System Settings → Network
```

3. **Run the enhanced server**:
```bash
python app_enhanced.py
```

4. **Open the dashboard**:
```
http://localhost:8000/dashboard
```

### On Your Phone (Edge Node)

1. **Install Python app** (like Pythonista or Pyto)

2. **Update SERVER_URL** in `phone_node_enhanced.py`:
```python
SERVER_URL = "http://YOUR_MAC_IP:8000"  # Use IP from step 2 above
```

3. **Run the edge node**:
```bash
python phone_node_enhanced.py
```

## 🎨 Understanding the Dashboard

### Color Coding
- 🟢 **Green**: Healthy/Completed/Alive
- 🔵 **Blue**: Working/In Progress
- 🟡 **Yellow**: Idle/Pending
- 🔴 **Red**: Failed/Dead/Error

### Live Updates
- Dashboard auto-refreshes every 2 seconds
- Pulsing indicator in top-right shows live status
- Recent tasks shown in chronological order

## 📱 Phone Node Console Output

The enhanced phone node provides rich console feedback:

```
[14:23:15] 🚀 Starting node phone-node-1
[14:23:15] 🌐 Connecting to server: http://10.39.86.168:8000
[14:23:16] 💓 Heartbeat sent successfully
[14:23:18] 🔍 Polling for new task...
[14:23:18] 📥 Received task: task-00001 (type: compute_congestion)
[14:23:18]    └─ Assigned at: 2025-02-10T14:23:18
[14:23:18] ⚙️ Processing task task-00001...
[14:23:18]    └─ Computing congestion metrics...
[14:23:20] ✨ Task task-00001 processed in 2.01s
[14:23:20] 📤 Sending result for task-00001 (status: completed)
[14:23:20] ✅ Task task-00001 result sent successfully
[14:23:20] 🎉 Task task-00001 completed successfully!
```

## 🛠️ API Endpoints

### Status and Monitoring
- `GET /` - Redirects to dashboard
- `GET /dashboard` - Real-time monitoring interface
- `GET /status` - JSON system status
- `GET /summary` - Congestion metrics

### Node Operations
- `POST /node/heartbeat` - Register node heartbeat
  ```json
  {"node": "phone-node-1", "status": "alive", "timestamp": 1234567890}
  ```

### Task Management
- `GET /task?node_id=<id>` - Fetch next task
- `POST /task-result` - Submit task result
  ```json
  {
    "task_id": "task-00001",
    "node_id": "phone-node-1",
    "status": "completed",
    "result": {...},
    "processing_time_seconds": 2.01
  }
  ```

## 📈 Statistics Examples

### Server Logs
```
2025-02-10 14:23:15 [INFO] ✅ New node registered: phone-node-1
2025-02-10 14:23:18 [INFO] 📋 Task created: task-00001 (type: compute_congestion)
2025-02-10 14:23:18 [INFO] 🎯 Task task-00001 assigned to phone-node-1
2025-02-10 14:23:20 [INFO] ✅ Task task-00001 completed by phone-node-1 in 2.0s
```

### Node Statistics (printed every 30s)
```
============================================================
📊 NODE STATISTICS (phone-node-1)
============================================================
⏱️  Uptime: 180s (3.0 minutes)
💓 Heartbeats: 36 sent, 0 failed
📋 Tasks: 12 fetched, 11 completed, 1 failed
⚡ Average task time: 2.15s
============================================================
```

## 🔧 Configuration Options

### Server (`app_enhanced.py`)
```python
CYCLE_SECONDS = 45          # How often to generate new tasks
NODE_TIMEOUT_SECONDS = 30   # Mark node dead after no heartbeat
TASK_TIMEOUT_SECONDS = 60   # Requeue task if not completed
```

### Client (`phone_node_enhanced.py`)
```python
HEARTBEAT_INTERVAL = 5      # Send heartbeat every 5s
TASK_POLL_INTERVAL = 3      # Check for tasks every 3s
MAX_RETRIES = 3             # Retry failed requests 3 times
TIMEOUT = 5                 # Request timeout in seconds
```

## 🐛 Troubleshooting

### Phone can't connect to Mac
1. Ensure both devices are on the same WiFi network
2. Check Mac's firewall settings (allow port 8000)
3. Verify the IP address is correct
4. Try `ping YOUR_MAC_IP` from phone

### No tasks appearing
1. Check dashboard to see if tasks are being generated
2. Verify `CYCLE_SECONDS` isn't too long
3. Check server logs for errors
4. Ensure node is sending heartbeats (check dashboard)

### Tasks timing out
1. Increase `TASK_TIMEOUT_SECONDS` on server
2. Decrease `time.sleep(2)` in task processing
3. Check network latency between devices

## 🎯 Next Steps

1. **Add more task types**: Extend `process_task()` function
2. **Implement real computation**: Replace mock data with actual analysis
3. **Add task priorities**: Modify queue to support priority ordering
4. **Scale to more nodes**: Add laptop, tablet, or Raspberry Pi nodes
5. **Persistent storage**: Save task history to database
6. **Alerts**: Add notifications for failed nodes or tasks

## 📝 Logging Emoji Guide

### Server
- 🚀 Startup
- ✅ Success/Completion
- 📋 Task creation
- 🎯 Task assignment
- ⚠️ Warning
- ❌ Error/Failure
- 💀 Node death
- ⏰ Timeout
- 🔄 Retry/Requeue

### Client
- 🚀 Startup
- 💓 Heartbeat success
- 💔 Heartbeat failure
- 🔍 Polling for task
- 📥 Task received
- 📭 No tasks available
- ⚙️ Processing
- ✨ Processing complete
- 📤 Sending result
- ✅ Result sent
- 🎉 Task fully complete
- ❌ Failure
- 💥 Exception
- 👋 Shutdown

## 🎓 Learning Resources

This system demonstrates:
- RESTful API design
- Distributed task queuing
- Real-time monitoring
- Heartbeat-based health checking
- Automatic failover (timeout → requeue)
- Thread-safe data structures
- Async/concurrent processing

Perfect for learning about distributed systems, edge computing, and microservices architecture!