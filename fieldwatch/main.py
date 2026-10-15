"""Local review workspace. Public hosting requires a separate access-control review."""
import json
import logging
import os
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlsplit

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fieldwatch import __version__
from fieldwatch.catalog import examples, find_example, optical_preview, radar_path
from fieldwatch.engine import InvalidRaster, MAX_BYTES
from fieldwatch.limits import RequestLimits
from fieldwatch.service import run_analysis

STATIC = Path(__file__).parent / "static"
SLOTS = BoundedSemaphore(2)
app = FastAPI(title="FieldWatch", version=__version__, description="Satellite surface-water evidence and human inspection review. Not emergency guidance.")
app.add_middleware(RequestLimits)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])


@app.middleware("http")
async def boundaries(request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and urlsplit(origin).netloc != request.headers.get("host"):
        response = JSONResponse({"detail":"Cross-origin analysis requests are not allowed."}, 403)
    else:
        response = await call_next(request)
    response.headers.update({"X-Content-Type-Options":"nosniff", "Referrer-Policy":"no-referrer", "X-Frame-Options":"DENY", "Cache-Control":"no-store",
        "Content-Security-Policy":"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
    return response


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status":"ok", "version":__version__, "opencv":cv2.__version__, "deployment":os.getenv("FIELDWATCH_DEPLOYMENT","local"),
            "demo_ready":all(item["available"] for item in examples()), "cool_verified":False}


@app.get("/api/examples")
def list_examples():
    return examples()


def execute(raw, **kwargs):
    if not SLOTS.acquire(False):
        raise HTTPException(429, "Two analyses are already running. Please retry shortly.")
    try:
        return run_analysis(raw, **kwargs)
    except InvalidRaster as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception as exc:
        logging.getLogger(__name__).error("Analysis failed (%s)", type(exc).__name__)
        raise HTTPException(500, "Analysis failed. No result was produced.") from None
    finally:
        SLOTS.release()


def parse_zones(text):
    if not text:
        return None
    if len(text.encode('utf-8')) > 200_000:
        raise HTTPException(413, "Zone GeoJSON exceeds 200 KB.")
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        raise HTTPException(422, "Zones must be valid GeoJSON.") from None


@app.post("/api/examples/{identifier}/analyze")
async def analyze_example(identifier: str, request: Request):
    item = find_example(identifier)
    if not item:
        raise HTTPException(404, "Example not found.")
    if not radar_path(item).is_file():
        raise HTTPException(503, "Download the public demo first: python scripts/fetch_fieldwatch_data.py --split demo")
    raw_body = await request.body()
    zones = parse_zones(raw_body.decode("utf-8", errors="replace")) if raw_body else None
    result = await run_in_threadpool(execute, radar_path(item).read_bytes(), name=item["title"], observed_on=item["date"], zones=zones)
    result["images"]["optical"] = await run_in_threadpool(optical_preview, item)
    result["context"] = {"dataset":"Sen1Floods11 v1.1", "chip":item["chip"], "source":"https://github.com/cloudtostreet/Sen1Floods11",
                         "attribution":"Bonafilia, Tellman, Anderson & Issenberg (2020), Cloud to Street. Contains modified Copernicus Sentinel data.",
                         "optical_date":item["optical_date"], "optical_use":"Visual context only; no cloud mask applied, not used for classification.",
                         "historical":True, "split":"training example; not held-out evaluation"}
    return result


@app.post("/api/analyze")
async def analyze_upload(request: Request):
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(415, "Upload GeoTIFF files as multipart/form-data.")
    async with request.form(max_files=2, max_fields=5, max_part_size=200_000) as form:
        allowed = {"current", "reference", "observed_on", "reference_on", "same_orbit", "zones"}
        if any(key not in allowed for key in form) or len(form.multi_items()) != len(form):
            raise HTTPException(422, "Unexpected or duplicate form fields.")
        current, earlier = form.get("current"), form.get("reference")
        if not isinstance(current, UploadFile) or (earlier is not None and not isinstance(earlier, UploadFile)):
            raise HTTPException(422, "Choose a current VV/VH GeoTIFF and optionally an earlier GeoTIFF.")
        for key in ("observed_on", "reference_on", "same_orbit", "zones"):
            if key in form and not isinstance(form[key], str):
                raise HTTPException(422, "Metadata fields must be text.")
        raw = await current.read(MAX_BYTES+1)
        reference = await earlier.read(MAX_BYTES+1) if earlier else None
        if len(raw) > MAX_BYTES or (reference is not None and len(reference) > MAX_BYTES):
            raise HTTPException(413, "Each GeoTIFF must be no larger than 24 MiB.")
        return await run_in_threadpool(execute, raw, name="Uploaded study area", observed_on=form.get("observed_on") or None,
            reference_raw=reference, reference_on=form.get("reference_on") or None, same_orbit=form.get("same_orbit") == "true", zones=parse_zones(form.get("zones")))


app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
