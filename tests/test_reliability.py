"""Additional formats and abstention cases, with an independent image renderer."""
from xml.etree import ElementTree
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.vision import analyze, fit_axis, number, reconstruction_svg, verify_reconstruction
from scripts.stress_cases import cases, chart_bytes


@pytest.mark.parametrize("case", list(cases()), ids=lambda c: c["id"])
def test_independent_renderings(case):
    result = analyze(case["image"], "unknown.png")
    assert result["status"] == case["expected"], result["findings"]
    if case["expected_issue"]:
        assert case["expected_issue"] in {f["kind"] for f in result["findings"]}
    if case["expected"] == "review":
        assert result["reconstruction"] is None
        assert result["bars"] == []
        return
    assert len(result["bars"]) == len(case["values"])
    tolerance = max(case["values"]) * .015
    for bar, actual in zip(result["bars"], case["values"]):
        assert abs(bar["value"]-actual) < tolerance
        assert bar["pixel_fit_range"][0] <= bar["value"] <= bar["pixel_fit_range"][1]
    assert result["trace"][-1]["metrics"]["geometry_verified"] is True
    if case["id"] in {"grayscale", "black-truncated", "mixed-color-gray"}:
        assert result["geometry"]["method"] == "luminance"
    if case["id"] == "compact-currency":
        assert result["axis"]["unit"] == "$"


@pytest.mark.parametrize(("text", "expected"), [("$1.5k", 1500), ("2M", 2e6), (".25", .25), ("1,200.50", 1200.5), ("25%", 25), ("1,2,3", None), ("1,5", None), ("9O", None), ("$20%", None), ("1e3", None)])
def test_strict_numeric_formats(text, expected):
    assert number(text) == expected


def test_mixed_currency_axis_is_not_calibrated():
    assert fit_axis([{"cy": 100, "value": 30, "unit": "$"}, {"cy": 200, "value": 20, "unit": "%"}, {"cy": 300, "value": 10, "unit": "$"}]) is None


def test_renderer_verification_detects_corrupted_heights():
    bars = [{"value": 92, "color": "#225588", "label": "A"}, {"value": 98, "color": "#225588", "label": "B"}]
    svg = reconstruction_svg(bars, "")
    assert verify_reconstruction(svg, bars)
    root = ElementTree.fromstring(svg)
    root.find("{http://www.w3.org/2000/svg}rect[@data-chart-bar='true']").set("height", "20")
    assert not verify_reconstruction(ElementTree.tostring(root, encoding="unicode"), bars)
    assert not verify_reconstruction("not XML", bars)


def test_small_values_keep_precision_in_reconstruction():
    bars = [{"value": .00012, "color": "#225588", "label": "A"}]
    svg = reconstruction_svg(bars, "")
    assert "0.00012" in svg
    assert verify_reconstruction(svg, bars)


def test_missing_baseline_tick_does_not_get_extrapolated():
    path = Path(__file__).resolve().parents[1] / "app/static/samples/honest.png"
    with Image.open(path) as image:
        image = image.convert("RGB")
        ImageDraw.Draw(image).rectangle((130, 680, 188, 715), fill="white")
        buffer = BytesIO()
        image.save(buffer, "PNG")
    result = analyze(buffer.getvalue())
    assert result["status"] == "review"
    assert result["reconstruction"] is None
    assert any(t["action"] == "Reinspect axis crop" for t in result["trace"])


def test_render_failure_withholds_reconstruction(monkeypatch):
    monkeypatch.setattr("app.vision.reconstruction_svg", lambda *args: "<svg/>")
    case = next(cases())
    result = analyze(case["image"])
    assert result["status"] == "review"
    assert result["reconstruction"] is None
    assert result["bars"] == []
    assert result["trace"][-1]["metrics"]["geometry_verified"] is False


def test_evaluator_does_not_hide_missing_bars_or_wrong_issue():
    from scripts.evaluate import score_case
    case = {"id": "sample", "expected": "flagged", "expected_issue": "truncated_axis", "values": [92, 98]}
    result = {"status": "flagged", "bars": [{"value": 92}], "findings": [{"kind": "inverted_axis"}], "reconstruction": "<svg/>", "processing_ms": 1, "trace": []}
    score = score_case(case, result)
    assert score["correct"] is False
    assert score["decision_correct"] is False
    assert score["value_count_correct"] is False
    assert score["mean_absolute_error"] is None


def test_small_nonzero_baseline_is_not_rounded_to_zero():
    raw = chart_bytes([22, 44, 61, 78], limits=(1.5, 100), ticks=(1.5, 20, 40, 60, 80, 100))
    result = analyze(raw)
    assert result["status"] == "flagged"
    assert result["axis"]["baseline"] > 0
    assert any(f["kind"] == "truncated_axis" for f in result["findings"])


def test_uncertain_baseline_without_zero_tick_is_not_cleared():
    raw = chart_bytes([22, 44, 61, 78], limits=(1, 100), ticks=(1, 20, 40, 60, 80, 100), label_format=lambda v: f"{v:.1f}")
    result = analyze(raw)
    assert result["status"] == "review"
    assert result["reconstruction"] is None
    assert any(f["kind"] == "baseline_uncertain" for f in result["findings"])
