import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router as api_router
from app.database import init_db
from app.services.agentic_loop import DATA_DIR
from app.services.analysis_worker import worker
from app.services import governance
from app.services.camera_ingestion import manager as camera_manager
from app.database import get_db_connection


@asynccontextmanager
async def lifespan(app):
    worker.start()
    camera_manager.start_configured()
    try:
        yield
    finally:
        camera_manager.stop_all()
        worker.stop()

# Ensure DB & static directories exist
init_db()
os.makedirs(os.path.join(DATA_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "crops"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "reports"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "evidence"), exist_ok=True)

app = FastAPI(
    title="LotTrace API",
    description="Local dealership vehicle and licence-plate video investigation",
    version="0.1.0",
    lifespan=lifespan,
)

allowed_origins = [origin.strip() for origin in os.environ.get("AIEYE_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
        "font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'",
    )
    return response


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    # CORS alone does not prevent cross-origin form POSTs changing local sessions.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins:
            return JSONResponse({"detail":"This local application does not accept requests from that origin."},status_code=403)
    return await call_next(request)

@app.middleware("http")
async def authenticated_access(request: Request, call_next):
    path=request.url.path
    public=path=="/" or path.startswith("/api/auth/") or path=="/api/auth/status"
    if request.method=="OPTIONS" or public:
        return await call_next(request)
    if path.startswith(("/api", "/uploads", "/crops", "/evidence")):
        if not governance.configured():
            return JSONResponse({"detail":"LotTrace setup is required."},status_code=428)
        user=governance.authenticate(request.cookies.get("lottrace_session"))
        if not user:
            return JSONResponse({"detail":"Authentication required."},status_code=401)
        if not governance.permitted(user["role"],request.method,path):
            return JSONResponse({"detail":"Your role does not permit this action."},status_code=403)
        request.state.user=user
        parts=path.strip("/").split("/")
        with get_db_connection() as conn:
            owner=None
            if len(parts)>=3 and parts[0]=="api" and parts[1]=="sessions":
                row=conn.execute("SELECT dealership_id FROM sessions WHERE session_id=?",(parts[2],)).fetchone(); owner=row[0] if row else None
            elif len(parts)>=3 and parts[0]=="api" and parts[1]=="vehicle-sightings":
                row=conn.execute("SELECT dealership_id FROM vehicle_sightings WHERE sighting_id=?",(parts[2],)).fetchone(); owner=row[0] if row else None
            elif len(parts)>=3 and parts[0]=="evidence" and parts[1]=="inspections":
                row=conn.execute("SELECT dealership_id FROM inspections WHERE inspection_id=?",(parts[2],)).fetchone(); owner=row[0] if row else "missing"
            elif len(parts)>=3 and parts[0]=="evidence" and parts[1]=="exports":
                export_id=os.path.splitext(parts[2])[0]
                row=conn.execute("SELECT i.dealership_id FROM evidence_exports e JOIN incidents i ON i.incident_id=e.incident_id WHERE e.export_id=?",(export_id,)).fetchone(); owner=row[0] if row else "missing"
            elif len(parts)>=2 and parts[0] in ("uploads","crops","evidence"):
                row=conn.execute("SELECT dealership_id FROM sessions WHERE session_id=?",(parts[1],)).fetchone(); owner=row[0] if row else "missing"
        if owner is not None and owner!=user["dealership_id"]:
            return JSONResponse({"detail":"Record not found."},status_code=404)
    return await call_next(request)

# Static files mount
app.mount("/uploads", StaticFiles(directory=os.path.join(DATA_DIR, "uploads")), name="uploads")
app.mount("/crops", StaticFiles(directory=os.path.join(DATA_DIR, "crops")), name="crops")
app.mount("/evidence", StaticFiles(directory=os.path.join(DATA_DIR, "evidence")), name="evidence")

# Include API Router
app.include_router(api_router)

# Desktop distributions point this at the packaged Vite build. Development
# continues to use Vite directly, so the API remains independently testable.
frontend_dir = os.environ.get("LOTTRACE_FRONTEND_DIR")
if frontend_dir and (Path(frontend_dir) / "index.html").is_file():
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="desktop-app")

@app.get("/")
def read_root():
    return {
        "app": "LotTrace",
        "status": "online",
        "description": "Local dealership vehicle video investigator"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
