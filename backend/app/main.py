import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router as api_router
from app.database import init_db
from app.services.agentic_loop import DATA_DIR

# Ensure DB & static directories exist
init_db()
os.makedirs(os.path.join(DATA_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "crops"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "reports"), exist_ok=True)

app = FastAPI(
    title="AeroFind Agent API",
    description="Agentic Post-Flight Drone-Footage Analysis Platform for Search and Rescue Operations",
    version="1.0.0"
)

# Enable CORS for local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mount
app.mount("/uploads", StaticFiles(directory=os.path.join(DATA_DIR, "uploads")), name="uploads")
app.mount("/crops", StaticFiles(directory=os.path.join(DATA_DIR, "crops")), name="crops")
app.mount("/reports", StaticFiles(directory=os.path.join(DATA_DIR, "reports")), name="reports")

# Include API Router
app.include_router(api_router)

@app.get("/")
def read_root():
    return {
        "app": "AeroFind Agent",
        "status": "online",
        "description": "Agentic SAR drone footage analysis platform"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
