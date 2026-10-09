import numpy as np
import pytest

from app.vision import analyze, decode_image
from scripts.stress_cases import chart_bytes
from scripts.evaluate_variants import score_variant, variants


@pytest.mark.parametrize("name,raw", list(variants(chart_bytes([0, 44, 61, 78]))))
def test_image_transforms_do_not_turn_missing_categories_into_a_clear_chart(name, raw):
    result = analyze(raw)
    assert result["status"] == "review", name
    assert result["bars"] == [] and result["reconstruction"] is None


def test_exif_orientation_is_normalized_before_geometry():
    original = chart_bytes([22, 44, 61, 78])
    raw = dict(variants(original))["exif-rotated-jpeg"]
    decoded = decode_image(raw)
    assert decoded.shape == (640, 960, 3)
    # JPEG is lossy; compare the normalized image, not its byte digest.
    assert np.mean(np.abs(decoded.astype(float)-decode_image(original).astype(float))) < 2


def test_variant_scorer_distinguishes_refusal_from_reconstruction():
    case = {"id": "sample", "expected": "clear", "values": [10, 20]}
    result = {"status": "review", "bars": [], "findings": [], "reconstruction": None, "processing_ms": 1, "trace": []}
    score = score_variant(case, result)
    assert score["safe"] and score["refused"] and not score["correct"]
    assert not score["accepted"]


@pytest.mark.parametrize("status,bars,svg", [
    ("clear", [{"value": 10}], "<svg/>"),
    ("clear", [{"value": 10}, {"value": 200}], "<svg/>"),
    ("review", [{"value": 10}], None),
    ("review", [], "<svg/>"),
])
def test_variant_scorer_does_not_hide_incorrect_or_partial_outputs(status, bars, svg):
    case = {"id": "sample", "expected": "clear", "values": [10, 20]}
    result = {"status": status, "bars": bars, "findings": [], "reconstruction": svg, "processing_ms": 1, "trace": []}
    assert not score_variant(case, result)["safe"]
