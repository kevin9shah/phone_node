# 🚀 Quick Start Guide

Get your transparent distributed task system running in 5 minutes!

## Step 1: Prepare Your Mac (30 seconds)

```bash
# Install dependencies
pip install fastapi uvicorn requests pydantic

# Find your Mac's IP address
ipconfig getifaddr en0
# Example output: 10.39.86.168
# Write this down! You'll need it for Step 3.
```

## Step 2: Start the Server (10 seconds)

```bash
# Run the enhanced server
python app_enhanced.py

# You should see:
# INFO:     Started server process
# INFO:     Uvicorn running on http://0.0.0.0:8000
# 🚀 Server started - distributed task system online
```

**Open your dashboard immediately:**
```
http://localhost:8000/dashboard
```

You should see a beautiful purple-themed dashboard!

## Step 3: Configure Your Phone (1 minute)

1. **Install a Python app** on your phone:
   - iOS: Pythonista (paid) or Pyto (free)
   - Android: Pydroid 3 (free)

2. **Edit `phone_node_enhanced.py`** (line 13):
   ```python
   # Change this line:
   SERVER_URL = "http://10.39.86.168:8000"
   
   # To your Mac's IP from Step 1:
   SERVER_URL = "http://YOUR_MAC_IP:8000"
   ```

3. **Make sure both devices are on the same WiFi network!**

## Step 4: Start Your Phone Node (10 seconds)

```bash
# Run on your phone
python phone_node_enhanced.py

# You should see a startup banner:
# ============================================================
# 🤖 DISTRIBUTED EDGE NODE
# ============================================================
# Node ID: phone-node-1
# Server: http://10.39.86.168:8000
# ...
```

## Step 5: Watch the Magic! ✨

1. **On your Mac's dashboard** (`http://localhost:8000/dashboard`):
   - You'll see your phone node appear under "Active Nodes"
   - Watch tasks get assigned in real-time
   - See completion statistics update

2. **On your phone's console**:
   - Beautiful emoji-rich logging
   - Task processing updates
   - Statistics every 30 seconds

3. **On your Mac's terminal**:
   - Server logs with task assignments
   - Completion notifications
   - Performance metrics

## 🎯 What You Should See

### Mac Dashboard
```
📊 System Overview
Total Nodes: 1
Alive Nodes: 1
Working Nodes: 1
Dead Nodes: 0

📋 Task Statistics
Total Tasks: 5
Pending: 2
Assigned: 1
Completed: 2
Failed: 0
Queue Size: 2

🖥️ Active Nodes
phone-node-1 ● WORKING
Last heartbeat: 2s ago
Tasks: ✓2 ✗0 ⚙️ task-00003
```

### Phone Console
```
[14:23:15] 🚀 Starting node phone-node-1
[14:23:16] 💓 Heartbeat sent successfully
[14:23:18] 📥 Received task: task-00001 (type: compute_congestion)
[14:23:18] ⚙️ Processing task task-00001...
[14:23:20] ✨ Task task-00001 processed in 2.01s
[14:23:20] ✅ Task task-00001 result sent successfully
[14:23:20] 🎉 Task task-00001 completed successfully!
```

### Mac Terminal
```
2025-02-10 14:23:15 [INFO] ✅ New node registered: phone-node-1
2025-02-10 14:23:18 [INFO] 📋 Task created: task-00001 (type: compute_congestion)
2025-02-10 14:23:18 [INFO] 🎯 Task task-00001 assigned to phone-node-1
2025-02-10 14:23:20 [INFO] ✅ Task task-00001 completed by phone-node-1 in 2.0s
```

## 🐛 Troubleshooting

### Phone can't connect?
```bash
# On Mac - check if server is accessible
curl http://localhost:8000/summary

# On phone - try accessing dashboard in browser
# http://YOUR_MAC_IP:8000/dashboard
# If this doesn't load, it's a network issue
```

**Common fixes:**
1. ✅ Both devices on same WiFi
2. ✅ Mac firewall allows port 8000
3. ✅ Correct IP address in phone_node_enhanced.py
4. ✅ Server is actually running on Mac

### No tasks showing up?
The server creates tasks every 45 seconds. Just wait a bit or:

```python
# In app_enhanced.py, change line 15:
CYCLE_SECONDS = 10  # Faster task generation!
```

### Phone node keeps disconnecting?
Increase heartbeat interval:

```python
# In phone_node_enhanced.py, change line 13:
HEARTBEAT_INTERVAL = 10  # Less frequent heartbeats
```

## 🎉 Success Indicators

You know it's working when:
- ✅ Dashboard shows your phone node as "ALIVE" or "WORKING"
- ✅ "Recent Tasks" section is updating
- ✅ Phone console shows task completions
- ✅ Task counter is increasing

## 📱 Next: Add More Nodes!

Once you have Mac + Phone working, try:

```python
# On another device (laptop, tablet, raspberry pi)
# Just change the NODE_ID:
NODE_ID = "laptop-node-1"  # or "tablet-node-1", etc.

# Then run:
python phone_node_enhanced.py
```

All nodes will appear in the dashboard and share the workload!

## 🎓 Understanding the Flow

```
1. Server creates task every 45s
   ↓
2. Task added to queue
   ↓
3. Phone polls for tasks (every 3s)
   ↓
4. Server assigns task to phone
   ↓
5. Phone processes task (~2s)
   ↓
6. Phone sends result back
   ↓
7. Server marks task as complete
   ↓
8. Dashboard updates in real-time
```

## 🔥 Pro Tips

1. **Keep the dashboard open** - It's hypnotic to watch!
2. **Check stats every 30s** on phone console
3. **Monitor server logs** in Mac terminal
4. **Try killing the phone app** - Watch it get marked as "DEAD" then come back "ALIVE"!
5. **Let it run overnight** - See how many tasks complete!

## 📊 Expected Performance

- Task creation: 1 every 45 seconds
- Task processing: ~2 seconds per task
- Heartbeats: Every 5 seconds
- Dashboard refresh: Every 2 seconds
- Phone polls: Every 3 seconds

With 1 phone node, you should complete ~80 tasks per hour!

---

**Need help?** Check README.md for full documentation or IMPROVEMENTS.md to see what changed from your original code.

**Have fun watching your distributed system work!** 🎉