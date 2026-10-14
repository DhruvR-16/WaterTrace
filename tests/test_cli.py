from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.cli import main, MAX_UPLOAD


def fake_result(status="clear"):
    return {"status": status, "filename": "chart.png", "source_sha256": "fixture-digest",
            "image": "private-image-payload", "reconstruction": "<svg/>", "engine": {"policy": "test"}}


@pytest.mark.parametrize("status,strict,expected", [
    ("clear", False, 0), ("clear", True, 0), ("flagged", False, 0),
    ("flagged", True, 1), ("review", False, 0), ("review", True, 1),
])
def test_exit_codes_and_report_privacy(tmp_path, monkeypatch, status, strict, expected):
    image = tmp_path / "chart.png"
    image.write_bytes(b"pixels")
    monkeypatch.setattr("app.cli.analyze", lambda *args: fake_result(status))
    out = StringIO()
    assert main([str(image)] + (["--fail-on-findings"] if strict else []), out=out) == expected
    report = json.loads(out.getvalue())
    assert report["summary"][status] == 1
    assert "private-image-payload" not in out.getvalue() and "<svg" not in out.getvalue()
    assert str(tmp_path) not in out.getvalue()


def test_batch_continues_after_bad_files_and_preserves_order(tmp_path, monkeypatch):
    good = tmp_path / "good.png"
    good.write_bytes(b"pixels")
    monkeypatch.setattr("app.cli.analyze", lambda *args: fake_result())
    out = StringIO()
    assert main([str(tmp_path / "missing.png"), str(good)], out=out) == 2
    report = json.loads(out.getvalue())
    assert report["summary"]["completed"] == 1 and report["summary"]["errors"] == 1
    assert report["errors"][0]["filename"] == "missing.png"
    assert report["errors"][0]["input_index"] == 1 and report["inspections"][0]["input_index"] == 2


def test_exclusive_private_output_never_overwrites(tmp_path, monkeypatch):
    image, output = tmp_path / "chart.png", tmp_path / "report.json"
    image.write_bytes(b"pixels")
    monkeypatch.setattr("app.cli.analyze", lambda *args: fake_result())
    assert main([str(image), "--output", str(output)]) == 0
    before = output.read_bytes()
    assert main([str(image), "--output", str(output)], err=StringIO()) == 2
    assert output.read_bytes() == before
    if os.name == "posix":
        assert output.stat().st_mode & 0o777 == 0o600


def test_input_cannot_be_used_as_output(tmp_path, monkeypatch):
    path = tmp_path / "chart.png"
    path.write_bytes(b"pixels")
    monkeypatch.setattr("app.cli.analyze", lambda *args: pytest.fail("must reject before reading input"))
    assert main([str(path), "--output", str(path)], err=StringIO()) == 2
    assert path.read_bytes() == b"pixels"


def test_oversized_input_is_not_sent_to_vision(tmp_path, monkeypatch):
    image = tmp_path / "large.png"
    with image.open("wb") as file:
        file.truncate(MAX_UPLOAD + 1)
    monkeypatch.setattr("app.cli.analyze", lambda *args: pytest.fail("must enforce file size before OCR"))
    out = StringIO()
    assert main([str(image)], out=out) == 2
    assert json.loads(out.getvalue())["errors"][0]["code"] == "file_too_large"


def test_unexpected_errors_do_not_print_private_diagnostics(tmp_path, monkeypatch):
    image = tmp_path / "chart.png"
    image.write_bytes(b"pixels")
    def broken(*args):
        raise RuntimeError("private OCR content /private/data.png")
    monkeypatch.setattr("app.cli.analyze", broken)
    out = StringIO()
    assert main([str(image)], out=out) == 2
    assert "private OCR content" not in out.getvalue()
    assert json.loads(out.getvalue())["errors"][0]["code"] == "inspection_failed"


def test_real_cli_runs_without_a_web_server():
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run([sys.executable, "-m", "app.cli", "app/static/samples/truncated.png", "--fail-on-findings"],
                             cwd=root, capture_output=True, text=True, timeout=30)
    assert process.returncode == 1, process.stderr
    report = json.loads(process.stdout)
    assert report["inspections"][0]["status"] == "flagged"
    assert len(report["inspections"][0]["source_sha256"]) == 64


def test_invalid_images_return_a_structured_error(tmp_path):
    image = tmp_path / "invalid.png"
    image.write_bytes(b"not an image")
    out = StringIO()
    assert main([str(image)], out=out) == 2
    assert json.loads(out.getvalue())["errors"][0]["code"] == "invalid_image"


def test_directories_are_not_recursively_scanned(tmp_path):
    out = StringIO()
    assert main([str(tmp_path)], out=out) == 2
    assert json.loads(out.getvalue())["errors"][0]["code"] == "unreadable_file"


def test_output_symlink_cannot_overwrite_its_target(tmp_path):
    target, link = tmp_path / "important.txt", tmp_path / "report.json"
    target.write_text("keep me")
    link.symlink_to(target)
    assert main([str(target), "--output", str(link)], err=StringIO()) == 2
    assert target.read_text() == "keep me"
