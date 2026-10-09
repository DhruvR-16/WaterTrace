"""Regression: omitted zero/short bars must not produce a partial clear chart."""
import json

import pytest

from app.vision import analyze, category_row_evidence
from scripts.stress_cases import chart_bytes


@pytest.mark.parametrize("values", [
    [0, 44, 61, 78], [1, 44, 61, 78], [22, 44, 61, 0],
    [22, 0, 61, 0], [0, 0, 61, 78],
])
def test_visible_categories_without_recoverable_bars_require_review(values):
    result = analyze(chart_bytes(values), "unknown.png")
    assert result["status"] == "review"
    assert result["bars"] == [] and result["reconstruction"] is None
    assert result["geometry"]["category_check"] == "mismatch"
    assert result["geometry"]["unmatched_category_words"]
    assert any(f["kind"] == "incomplete_categories" for f in result["findings"])
    assert any(o["label"].startswith("Unmatched category:") for o in result["overlays"])


def word(text, center, top=540, confidence=.95, width=40):
    return {"text": text, "box": [center-width/2, top, width, 16], "confidence": confidence}


def bars(*centers):
    return [{"box": [center-38, 200, 76, 320]} for center in centers]


def test_multiword_names_and_separate_footer_do_not_look_like_missing_categories():
    words = [word("North", 220), word("America", 270), word("South", 395), word("America", 445),
             word("Source:", 160, top=605), word("survey", 225, top=605)]
    row, unmatched = category_row_evidence(words, bars(240, 415), 140)
    assert [w["text"] for w in row] == ["North", "America", "South", "America"]
    assert unmatched == []


def test_unreadable_category_ocr_does_not_claim_completeness():
    assert category_row_evidence([], bars(240, 415), 140) == ([], [])
    assert category_row_evidence([word("only", 240)], bars(240, 415), 140) == ([], [])
    assert category_row_evidence([word("North", 240, confidence=.3), word("South", 415, confidence=.3)], bars(240, 415), 140) == ([], [])


def test_numeric_category_names_are_valid_evidence():
    row, unmatched = category_row_evidence([word("2020", 240), word("2021", 415), word("2022", 590)], bars(415, 590), 140)
    assert len(row) == 3 and [w["text"] for w in unmatched] == ["2020"]


def test_axis_side_text_does_not_become_a_category():
    row, unmatched = category_row_evidence([word("0", 120), word("North", 240), word("South", 415)], bars(240, 415), 140)
    assert len(row) == 2 and unmatched == []


def test_ocr_failure_report_does_not_expose_private_exception_text(monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("private OCR text from /private/local/path")
    monkeypatch.setattr("app.vision.ocr", failed)
    result = analyze(chart_bytes([22, 44, 61, 78]))
    assert result["status"] == "review"
    report = json.dumps({k: v for k, v in result.items() if k != "image"})
    assert "private OCR text" not in report and "/private/local/path" not in report
    assert result["trace"][-1]["metrics"]["error_type"] == "RuntimeError"
