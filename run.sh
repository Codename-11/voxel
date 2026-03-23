#!/bin/bash
# Voxel — Development launcher (starts backend + frontend)
set -e
cd "$(dirname "$0")"

echo "Starting Voxel..."
echo "  Backend:  uv run server.py (WebSocket :8080)"
echo "  Frontend: npm run dev (http://localhost:5173)"
echo ""

# Start backend in background
uv run server.py &
BACKEND_PID=$!

# Start frontend
cd app && npm run dev

# Cleanup backend on exit
kill $BACKEND_PID 2>/dev/null
