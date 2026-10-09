"""Exercise admission limits before any multipart parser or OCR work runs."""
import asyncio
import json

from fastapi.testclient import TestClient
import pytest
from starlette.responses import JSONResponse

from app.main import app, display_filename
from app.upload_limits import MAX_UPLOAD, MAX_REQUEST, UploadLimitsMiddleware

MULTIPART = (b"content-type", b"multipart/form-data; boundary=test")


def scope(headers=(), *, path="/api/analyze"):
    return {"type": "http", "method": "POST", "path": path, "headers": list(headers)}


async def exchange(middleware, messages, headers=(), *, path="/api/analyze"):
    remaining = list(messages)
    sent = []
    reads = 0

    async def receive():
        nonlocal reads
        reads += 1
        return remaining.pop(0) if remaining else {"type": "http.disconnect"}

    await middleware(scope(headers, path=path), receive, _sender(sent))
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start, json.loads(body) if body else None, reads


def _sender(sent):
    async def send(message):
        sent.append(message)
    return send


def receiver_app(calls):
    async def downstream(scope, receive, send):
        message = await receive()
        calls.append(message)
        await JSONResponse({"bytes": len(message.get("body", b""))})(scope, receive, send)
    return downstream


def chunk(body, more=False):
    return {"type": "http.request", "body": body, "more_body": more}


@pytest.mark.parametrize("headers,status", [
    ([MULTIPART, (b"content-length", b"17")], 413),
    ([MULTIPART, (b"content-length", b"-1")], 400),
    ([MULTIPART, (b"content-length", b"abc")], 400),
    ([MULTIPART, (b"content-length", b"0"), (b"content-length", b"0")], 400),
    ([MULTIPART, (b"content-length", b"0"), (b"transfer-encoding", b"chunked")], 400),
    ([MULTIPART, (b"content-length", b"9" * 5000)], 400),
    ([(b"content-type", b"application/json")], 415),
    ([], 415),
    ([MULTIPART, MULTIPART], 415),
    ([MULTIPART, (b"content-encoding", b"gzip")], 415),
])
def test_invalid_headers_rejected_without_reading_or_parsing(headers, status):
    calls = []
    middleware = UploadLimitsMiddleware(receiver_app(calls), max_request=16)
    start, result, reads = asyncio.run(exchange(middleware, [chunk(b"x")], headers))
    assert start["status"] == status
    assert isinstance(result["detail"], str)
    assert reads == 0 and calls == []


@pytest.mark.parametrize("declared", [None, b"1"])
def test_chunked_or_lying_length_cannot_bypass_total_limit(declared):
    calls = []
    middleware = UploadLimitsMiddleware(receiver_app(calls), max_request=16)
    headers = [MULTIPART] + ([(b"content-length", declared)] if declared else [])
    start, _, reads = asyncio.run(exchange(middleware, [chunk(b"a" * 10, True), chunk(b"b" * 7, True), chunk(b"unread")], headers))
    assert start["status"] == 413
    assert reads == 2 and calls == []


def test_exact_limit_is_replayed_once_without_losing_chunks():
    calls = []
    middleware = UploadLimitsMiddleware(receiver_app(calls), max_request=16)
    start, result, reads = asyncio.run(exchange(middleware, [chunk(b"a" * 8, True), chunk(b"b" * 8)], [MULTIPART]))
    assert start["status"] == 200 and result == {"bytes": 16}
    assert calls == [chunk(b"a" * 8 + b"b" * 8)] and reads == 2


def test_incorrect_declared_length_rejected_before_parser():
    calls = []
    middleware = UploadLimitsMiddleware(receiver_app(calls))
    start, _, _ = asyncio.run(exchange(middleware, [chunk(b"abc")], [MULTIPART, (b"content-length", b"2")]))
    assert start["status"] == 400 and calls == []


def test_disconnect_does_not_start_parser_or_hold_upload_slot():
    calls = []
    middleware = UploadLimitsMiddleware(receiver_app(calls), max_uploads=1)
    start, _, _ = asyncio.run(exchange(middleware, [chunk(b"partial", True), {"type": "http.disconnect"}], [MULTIPART]))
    assert start is None and calls == []
    start, _, _ = asyncio.run(exchange(middleware, [chunk(b"next")], [MULTIPART]))
    assert start["status"] == 200


def test_slow_upload_times_out_and_releases_slot():
    async def run():
        calls, sent = [], []
        middleware = UploadLimitsMiddleware(receiver_app(calls), timeout=.01, max_uploads=1)

        async def slow_receive():
            await asyncio.sleep(10)

        await middleware(scope([MULTIPART]), slow_receive, _sender(sent))
        assert sent[0]["status"] == 408 and calls == []
        start, _, _ = await exchange(middleware, [chunk(b"next")], [MULTIPART])
        assert start["status"] == 200
    asyncio.run(run())


def test_upload_admission_is_bounded_before_body_reads():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def held_app(scope, receive, send):
            entered.set()
            await release.wait()
            await receiver_app(calls)(scope, receive, send)

        middleware = UploadLimitsMiddleware(held_app, max_uploads=1)
        first = asyncio.create_task(exchange(middleware, [chunk(b"first")], [MULTIPART]))
        await entered.wait()
        try:
            start, _, reads = await exchange(middleware, [chunk(b"second")], [MULTIPART])
            assert start["status"] == 429 and reads == 0
            assert (b"retry-after", b"2") in start["headers"]
        finally:
            release.set()
            await first
        start, _, _ = await exchange(middleware, [chunk(b"third")], [MULTIPART])
        assert start["status"] == 200
    asyncio.run(run())


def test_cancelled_upload_releases_admission_slot():
    async def run():
        entered = asyncio.Event()
        middleware = UploadLimitsMiddleware(receiver_app([]), max_uploads=1)

        async def receive():
            entered.set()
            await asyncio.sleep(10)

        task = asyncio.create_task(middleware(scope([MULTIPART]), receive, _sender([])))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        start, _, _ = await exchange(middleware, [chunk(b"next")], [MULTIPART])
        assert start["status"] == 200
    asyncio.run(run())


def test_other_routes_are_not_buffered_by_upload_middleware():
    calls = []
    middleware = UploadLimitsMiddleware(receiver_app(calls), max_request=1)
    start, _, _ = asyncio.run(exchange(middleware, [chunk(b"other")], path="/other"))
    assert start["status"] == 200 and calls == [chunk(b"other")]


@pytest.mark.parametrize("filename,expected", [
    ("/private/reports/chart.png", "chart.png"),
    ("C:\\private\\reports\\chart.png", "chart.png"),
    ("chart\x00\n\u202e.png", "chart.png"),
    ("", "chart.png"), (None, "chart.png"), ("..", "chart.png"),
    ("a" * 200, "a" * 120), ("résumé.png", "résumé.png"),
])
def test_display_filename_omits_paths_controls_and_excess_length(filename, expected):
    assert display_filename(filename) == expected


def test_multipart_shape_and_error_cleanup(monkeypatch):
    import starlette.formparsers as parsers
    created = []
    original = parsers.SpooledTemporaryFile

    def record_file(*args, **kwargs):
        file = original(*args, **kwargs)
        created.append(file)
        return file

    monkeypatch.setattr(parsers, "SpooledTemporaryFile", record_file)
    with TestClient(app) as client:
        assert client.post("/api/analyze", files=[("file", ("one.png", b"a")), ("file", ("two.png", b"b"))]).status_code == 400
        assert client.post("/api/analyze", files={"file": ("one.png", b"a")}, data={"unexpected": "field"}).status_code == 400
        assert client.post("/api/analyze", files={"wrong_field": ("one.png", b"a")}).status_code == 422
        assert client.post("/api/analyze", files={"file": ("one.png", b"not an image")}).status_code == 422
    assert created and all(file.closed for file in created)


def test_file_size_limit_and_early_error_headers(monkeypatch):
    calls = []

    def fake_analysis(raw, filename):
        calls.append(len(raw))
        return {"engine": {}, "filename": filename}

    monkeypatch.setattr("app.main.analyze", fake_analysis)
    with TestClient(app) as client:
        response = client.post("/api/analyze", files={"file": ("chart.png", b"a" * MAX_UPLOAD)})
        assert response.status_code == 200
        assert calls == [MAX_UPLOAD]
        assert client.post("/api/analyze", files={"file": ("chart.png", b"a" * (MAX_UPLOAD + 1))}).status_code == 413
        response = client.post("/api/analyze", content=b"x", headers={"content-length": str(MAX_REQUEST + 1)})
        assert response.status_code == 413
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert calls == [MAX_UPLOAD]


def test_analysis_failure_does_not_leak_exception_or_hold_worker(monkeypatch, caplog):
    def broken(*args):
        raise RuntimeError("private-chart-content /private/upload.png")

    monkeypatch.setattr("app.main.analyze", broken)
    with TestClient(app) as client:
        for _ in range(3):
            response = client.post("/api/analyze", files={"file": ("chart.png", b"image")})
            assert response.status_code == 500
            assert response.json() == {"detail": "Inspection failed. Please retry with another image."}
        assert "private-chart-content" not in caplog.text and "/private/upload.png" not in caplog.text
        assert "RuntimeError" in caplog.text
        monkeypatch.setattr("app.main.analyze", lambda raw, filename: {"engine": {}, "filename": filename})
        response = client.post("/api/analyze", files={"file": ("C:\\private\\chart.png", b"image")})
        assert response.status_code == 200 and response.json()["filename"] == "chart.png"
