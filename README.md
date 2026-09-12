# 🛸 AI(EYE) in the sky

**Agentic Post-Flight Drone Footage Analysis Platform for Search & Rescue (SAR)**

`AI(EYE) in the sky` is an autonomous AI agent system designed for Search and Rescue teams. After a drone flight, the operator uploads the recorded MP4/MOV footage and optional DJI SRT flight telemetry. The platform autonomously executes a 2-stage scanning pipeline, tracks people across frames, extracts multi-attribute HSV color distributions, ranks target candidate matches, and generates downloadable SAR search reports.

---

## 🚀 How to Run `AI(EYE) in the sky`

### Option 1: One-Click Windows Launcher (Recommended)
Simply double-click the included batch file in the repository root:
```cmd
run_aieye.bat
```
This script will automatically:
1. Launch the FastAPI backend server on `http://localhost:8000`.
2. Launch the Vite React frontend UI on `http://localhost:5173`.
3. Open your default web browser directly to `http://localhost:5173`.

---

### Option 2: Manual Terminal Execution

#### 1. Start the Backend API (FastAPI)
In a terminal window in the project root:
```powershell
# Install requirements if not already done
pip install -r backend/requirements.txt

# Start backend server
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Start the Frontend UI (React 18 + Vite)
In a second terminal window:
```powershell
cd frontend
npm install
npm run dev
```

#### 3. Access Mission Control UI
Open your browser to:
- **Mission Control Web App:** [http://localhost:5173](http://localhost:5173)
- **API Interactive Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Testing & Demo Footage Generation

To generate synthetic test footage (`demo_drone_search.mp4`) and flight telemetry (`demo_drone_search.SRT`):
```powershell
python generate_demo_video.py
```

To run the automated E2E system test suite:
```powershell
python test_e2e.py
```
