#!/bin/bash

# Function to handle cleanup on exit
cleanup() {
    echo "Stopping services..."
    if [ -n "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null
    fi
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "Starting backend..."
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Warning: .venv not found. Running uvicorn using global python."
fi

uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend..."
cd frontend && npm run dev &
FRONTEND_PID=$!

echo "=================================================="
echo "Services are starting!"
echo "Backend API: http://localhost:8000"
echo "Frontend: Check terminal output for local URL (usually http://localhost:5173)"
echo "Press Ctrl+C to stop both services."
echo "=================================================="

# Wait for both processes
wait
