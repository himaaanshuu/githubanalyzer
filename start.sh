#!/bin/bash
# GitHub Intelligence - Start Script

set -e

echo "GitHub Intelligence - Starting..."

# Start backend
echo "Starting backend on port 8000..."
cd backend
source ../venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Start frontend
echo "Starting frontend on port 5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "========================================="
echo "  GitHub Intelligence is running!"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "========================================="
echo ""
echo "Press Ctrl+C to stop both services."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

wait
