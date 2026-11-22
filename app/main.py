from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="PCB Missing Component Detector",
    description="Automated Optical Inspection for PCB Missing Components (Task B)",
    version="0.1.0"
)

# Mount static directory for offline assets (plain HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
async def get_index():
    """Serve the single-page application entrypoint."""
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/api/health")
async def health_check():
    """Health check endpoint confirming offline backend availability."""
    return {
        "status": "healthy",
        "service": "PCB Missing Component Detector",
        "version": "0.1.0",
        "max_working_dim": 1920
    }
