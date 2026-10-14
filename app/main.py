from pathlib import Path
import json
import logging
import os
import shutil
from threading import Semaphore

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.upload_limits import MAX_UPLOAD, UploadLimitsMiddleware
from app.privacy import display_filename
from app.vision import InvalidImage, analyze

STATIC = Path(__file__).parent / "static"
WORKERS = Semaphore(2)
logger = logging.getLogger(__name__)
app = FastAPI(title="ChartCourt", version="0.3.0", description="An evidence-led visual audit for chart axes.")
app.add_middleware(UploadLimitsMiddleware)


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
        raise HTTPException(429, "Two inspections are already running. Please retry in a moment.", headers={"Retry-After": "2"})
    try:
        result = analyze(raw, name)
        result["engine"]["deployment"] = os.getenv("CHARTCOURT_DEPLOYMENT", "local")
        return result
    except InvalidImage as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        # Exceptions can contain paths, OCR text, or user data. Log only the type.
        logger.error("Inspection failed (%s)", type(exc).__name__)
        raise HTTPException(500, "Inspection failed. Please retry with another image.") from None
    finally:
        WORKERS.release()


@app.post("/api/analyze", openapi_extra={"requestBody": {
    "required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"], "additionalProperties": False,
        "properties": {"file": {"type": "string", "format": "binary"}},
    }}},
}})
async def inspect(request: Request):
    # Restrict multipart shape as well as total bytes. The context closes every
    # parsed file even when validation, decoding, or analysis raises an error.
    async with request.form(max_files=1, max_fields=0) as form:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "Choose one image in the file field.")
        raw = await file.read(MAX_UPLOAD + 1)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "Use an image up to 8 MB.")
        return await run_in_threadpool(run_analysis, raw, display_filename(file.filename))


@app.post("/api/samples/{sample_id}/analyze")
def inspect_sample(sample_id: str):
    allowed = {sample["id"] for sample in samples()}
    if sample_id not in allowed:
        raise HTTPException(404, "Example not found.")
    return run_analysis((STATIC / "samples" / f"{sample_id}.png").read_bytes(), f"{sample_id}.png")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
