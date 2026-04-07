#!/bin/bash
echo "🚀 Starting TaskForze Nexus Development Environment..."

# Trap Ctrl+C (SIGINT) and kill all child processes cleanly
trap "echo -e '\n🛑 Stopping all servers...'; kill 0" SIGINT SIGTERM EXIT

echo "🐍 Starting FastAPI backend on http://localhost:8000..."
# Start the backend in the background
source .venv/bin/activate && uvicorn nexus.main:app --reload --port 8000 &

echo "⚛️ Starting Next.js frontend on http://localhost:3000..."
# Start the frontend in the background
cd frontend && npm run dev &

echo ""
echo "✅ Both servers are running!"
echo "   - Frontend: http://localhost:3000"
echo "   - Backend:  http://localhost:8000"
echo "   Press Ctrl+C to stop both servers at once."
echo "--------------------------------------------------------"

# Wait for background processes so the script doesn't exit immediately
wait
