"""Exercise the real OpenCV + OCR pipeline, including changed pixels and refusal."""
import json
import hashlib
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import cv2
import numpy as np
from PIL import Image
import pytest
import pytesseract
from fastapi.testclient import TestClient

from app.main import app, MAX_UPLOAD, WORKERS
from app.vision import analyze, decode_image, fit_axis, InvalidImage, number, reconstruction_svg

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "app" / "static" / "samples"
TRUTH = json.loads((ROOT / "tests" / "fixtures" / "truth.json").read_text())
client = TestClient(app)


@pytest.mark.parametrize("fixture", TRUTH, ids=lambda x: x["id"])
def test_known_chart_pixels(fixture):
    result = analyze((SAMPLES / f"{fixture['id']}.png").read_bytes(), "unrelated-name.png")
    expected = fixture["expected"]
    assert result["engine"]["opencv"].startswith("5.")
    if expected == "review":
        assert result["status"] == "review"
        assert result["reconstruction"] is None
        assert any(t["action"] == "Reinspect axis crop" for t in result["trace"])
        assert result["trace"][-1]["action"] == "Request human review"
    else:
        assert result["status"] == ("clear" if expected == "clear" else "flagged")
        assert len(result["bars"]) == len(fixture["values"])
        for bar, truth in zip(result["bars"], fixture["values"]):
            assert abs(bar["value"] - truth) < .5
        assert any(f["kind"] == {"clear": "axis_checks_passed", "truncated": "truncated_axis", "inverted": "inverted_axis"}[expected] for f in result["findings"])
        svg = ElementTree.fromstring(result["reconstruction"])
        assert len(svg.findall("{http://www.w3.org/2000/svg}rect")) == len(fixture["values"]) + 1
    if expected == "truncated":
        assert abs(result["comparison"]["apparent_ratio"] - 4) < .1
        assert abs(result["comparison"]["value_ratio"] - 98/92) < .005
        assert abs(result["axis"]["baseline"] - 90) < .1


def test_recomputed_from_resized_jpeg_pixels():
    with Image.open(SAMPLES / "truncated.png") as image:
        image = image.convert("RGB").resize((1008, 672))
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=80)
    result = analyze(buffer.getvalue(), "honest.png")
    assert result["status"] == "flagged"
    assert any(f["kind"] == "truncated_axis" for f in result["findings"])
    assert abs(result["axis"]["baseline"] - 90) < .3


def test_removing_axis_changes_the_next_action():
    image = cv2.imread(str(SAMPLES / "truncated.png"))
    image[:, :205] = 255
    ok, data = cv2.imencode(".png", image)
    assert ok
    result = analyze(data.tobytes(), "truncated.png")
    assert result["status"] == "review"
    assert result["reconstruction"] is None
    assert any(t["tool"] == "read_axis_detail" for t in result["trace"])


def test_blank_image_is_not_cleared():
    ok, data = cv2.imencode(".png", np.full((600, 900, 3), 255, np.uint8))
    result = analyze(data.tobytes())
    assert result["status"] == "review"
    assert result["reconstruction"] is None


def test_upload_api_runs_analysis_and_rejects_invalid_files():
    response = client.post("/api/analyze", files={"file": ("renamed.png", (SAMPLES / "inverted.png").read_bytes(), "image/png")})
    assert response.status_code == 200
    assert response.json()["axis"]["inverted"] is True
    assert client.post("/api/analyze", files={"file": ("fake.png", b"not an image", "image/png")}).status_code == 422
    assert client.post("/api/analyze", files={"file": ("huge.png", b"x" * (MAX_UPLOAD+1), "image/png")}).status_code == 413


def test_sample_allowlist_and_health():
    assert client.get("/api/health").json()["ocr_available"] is True
    assert client.post("/api/samples/unknown/analyze").status_code == 404
    assert len(client.get("/api/samples").json()) == len(TRUTH)


def test_numeric_parser_does_not_invent_digits():
    assert number("−20") == -20
    assert number("$1,234.5") == 1234.5
    assert number("90%") == 90
    assert number("9O") is None
    assert number("1e3") is None


def test_report_identifies_actual_input_bytes():
    raw = (SAMPLES / "honest.png").read_bytes()
    result = analyze(raw)
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert sum(step["duration_ms"] for step in result["trace"]) == result["trace"][-1]["elapsed_ms"]


def test_nonlinear_ticks_do_not_pass_linear_fit():
    fit = fit_axis([{"cy": 100, "value": 1000}, {"cy": 200, "value": 100}, {"cy": 300, "value": 10}])
    assert fit is not None and fit[2] > .025
    assert fit_axis([{"cy": 100, "value": 10}, {"cy": 200, "value": 20}]) is None


def test_missing_ocr_returns_review(monkeypatch):
    def missing(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr("app.vision.ocr", missing)
    result = analyze((SAMPLES / "truncated.png").read_bytes())
    assert result["status"] == "review"
    assert result["findings"][0]["kind"] == "ocr_unavailable"
    assert result["reconstruction"] is None


def test_unsupported_image_formats_and_small_inputs():
    for size, fmt in [((50, 50), "PNG"), ((200, 200), "GIF")]:
        buffer = BytesIO()
        Image.new("RGB", size, "white").save(buffer, fmt)
        with pytest.raises(InvalidImage):
            decode_image(buffer.getvalue())


def test_reconstruction_escapes_ocr_text():
    svg = reconstruction_svg([{"value": 42, "color": "#225588", "label": "<script>&\""}], "%")
    root = ElementTree.fromstring(svg)
    assert root.find("{http://www.w3.org/2000/svg}script") is None
    assert "&lt;script&gt;" in svg


def test_busy_inspection_returns_retryable_status():
    assert WORKERS.acquire(blocking=False)
    assert WORKERS.acquire(blocking=False)
    try:
        assert client.post("/api/samples/truncated/analyze").status_code == 429
    finally:
        WORKERS.release()
        WORKERS.release()
