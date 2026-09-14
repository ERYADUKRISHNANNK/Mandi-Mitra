@echo off
REM Mandi Mitra - start both servers (Windows)
start "Mandi Mitra API" cmd /k "cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000"
start "Mandi Mitra PWA" cmd /k "cd frontend && npm run dev"
echo Backend: http://127.0.0.1:8000/docs
echo PWA:     http://localhost:5173
