from pathlib import Path
import json
import os
import shutil
from threading import Semaphore

import cv2
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.vision import InvalidImage, analyze

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 8 * 1024 * 1024
WORKERS = Semaphore(2)
app = FastAPI(title="ChartCourt", version="0.2.0", description="An evidence-led visual audit for chart axes.")


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return dict(status="ok" if shutil.which("tesseract") else "degraded", opencv=cv2.__version__,
                ocr_available=bool(shutil.which("tesseract")), deployment=os.getenv("CHARTCOURT_DEPLOYMENT", "local"),
                cool_verified=False)


@app.get("/api/samples")
def samples():
    return json.loads((STATIC / "samples" / "index.json").read_text())


def run_analysis(raw: bytes, name: str):
    if not WORKERS.acquire(blocking=False):
        raise HTTPException(429, "Two inspections are already running. Please retry in a moment.")
    try:
        result = analyze(raw, name)
        result["engine"]["deployment"] = os.getenv("CHARTCOURT_DEPLOYMENT", "local")
        return result
    except InvalidImage as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        WORKERS.release()


@app.post("/api/analyze")
def inspect(file: UploadFile = File(...)):
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Use an image smaller than 8 MB.")
    return run_analysis(raw, Path(file.filename or "chart.png").name)


@app.post("/api/samples/{sample_id}/analyze")
def inspect_sample(sample_id: str):
    allowed = {sample["id"] for sample in samples()}
    if sample_id not in allowed:
        raise HTTPException(404, "Example not found.")
    return run_analysis((STATIC / "samples" / f"{sample_id}.png").read_bytes(), f"{sample_id}.png")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
