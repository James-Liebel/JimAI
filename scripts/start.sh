#!/bin/bash
echo "Starting Private AI System..."

# Check Ollama
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Ollama: Running"
else
    echo "Starting Ollama..."
    ollama serve &
    sleep 3
fi

# Start backend
cd "$(dirname "$0")/../backend"
python -m uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

sleep 2

# Start frontend
cd "$(dirname "$0")/../frontend"
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "Services running:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  Ollama:   http://localhost:11434"
echo ""
echo "Run 'python scripts/test_models.py' to verify all models."

wait
