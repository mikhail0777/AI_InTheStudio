import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router as api_router
from app.database import init_db
from app.services.agentic_loop import DATA_DIR
from app.services.analysis_worker import worker


@asynccontextmanager
async def lifespan(app):
    worker.start()
    try:
        yield
    finally:
        worker.stop()

# Ensure DB & static directories exist
init_db()
os.makedirs(os.path.join(DATA_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "crops"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "reports"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "evidence"), exist_ok=True)

app = FastAPI(
    title="AI(EYE) in the sky API",
    description="Agentic Post-Flight Drone-Footage Analysis Platform for Search and Rescue Operations",
    version="1.1.0",
    lifespan=lifespan,
)

# Local workstation use only; account-level access control is not implemented.
allowed_origins = [origin.strip() for origin in os.environ.get("AIEYE_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    # CORS alone does not prevent cross-origin form POSTs changing local sessions.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins:
            return JSONResponse({"detail":"This local application does not accept requests from that origin."},status_code=403)
    return await call_next(request)

# Static files mount
app.mount("/uploads", StaticFiles(directory=os.path.join(DATA_DIR, "uploads")), name="uploads")
app.mount("/crops", StaticFiles(directory=os.path.join(DATA_DIR, "crops")), name="crops")
app.mount("/evidence", StaticFiles(directory=os.path.join(DATA_DIR, "evidence")), name="evidence")

# Include API Router
app.include_router(api_router)

@app.get("/")
def read_root():
    return {
        "app": "AI(EYE) in the sky",
        "status": "online",
        "description": "Agentic SAR drone footage analysis platform"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
