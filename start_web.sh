#!/bin/bash
# TaskSAT Web UI Start Script
# Safely starts/restarts the web server

PORT=${1:-5001}

# Kill any existing web server
pkill -f "tasknet_web.py" 2>/dev/null
sleep 1

# Start new server
echo "Starting TaskSAT Web UI on port $PORT..."
python src/smt/tasknet_web.py --port $PORT &

# Wait for server to start
sleep 2

# Check if it started successfully
if pgrep -f "tasknet_web.py" > /dev/null; then
    echo "✓ Web server started successfully!"
    echo "  Open: http://localhost:$PORT"
else
    echo "✗ Failed to start web server"
    exit 1
fi
