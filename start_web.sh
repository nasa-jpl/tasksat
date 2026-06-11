#!/bin/bash
# Start TaskSAT Web Interface
#
# Usage:
#   ./start_web.sh           # starts on port 5001 (default)
#   ./start_web.sh 8080      # starts on port 8080

PORT=${1:-5001}  # Use first argument as port, default to 5001

echo "Starting TaskSAT Web Interface on port $PORT..."
python src/smt/tasknet_web.py --port $PORT
