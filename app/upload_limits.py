"""Bound upload bodies before multipart parsing, including chunked requests."""
import asyncio
from threading import BoundedSemaphore

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_UPLOAD = 8 * 1024 * 1024
MAX_REQUEST = MAX_UPLOAD + 64 * 1024  # Allow a small multipart envelope.


class _BodyTooLarge(Exception):
    pass


class UploadLimitsMiddleware:
    """Buffer only bounded bodies, with per-process admission and read deadlines.

    A receive-wrapper alone can let the framework parse/spool a partial upload
    before rejecting it. Here the parser receives nothing until size checks pass.
    This is an application guard, not a substitute for proxy limits/rate limiting.
    """

    def __init__(self, app: ASGIApp, *, max_request: int = MAX_REQUEST,
                 timeout: float = 30, max_uploads: int = 2):
        self.app = app
        self.max_request = max_request
        self.timeout = timeout
        self.slots = BoundedSemaphore(max_uploads)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != "/api/analyze":
            await self.app(scope, receive, send)
            return

        async def reject(status: int, detail: str, *, retry: bool = False) -> None:
            response = JSONResponse({"detail": detail}, status_code=status,
                                    headers={"Retry-After": "2"} if retry else None)
            await response(scope, receive, send)

        headers = scope.get("headers", [])
        lengths = [v for k, v in headers if k.lower() == b"content-length"]
        declared = None
        if lengths:
            if (len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 20
                    or any(k.lower() == b"transfer-encoding" for k, _ in headers)):
                await reject(400, "Invalid request length.")
                return
            declared = int(lengths[0])
            if declared > self.max_request:
                await reject(413, "Upload is too large. Use one image up to 8 MB.")
                return
        content_types = [v for k, v in headers if k.lower() == b"content-type"]
        if len(content_types) != 1 or content_types[0].split(b";", 1)[0].strip().lower() != b"multipart/form-data":
            await reject(415, "Send one image as multipart/form-data in the file field.")
            return
        if any(k.lower() == b"content-encoding" and v.strip().lower() != b"identity" for k, v in headers):
            await reject(415, "Compressed request bodies are not supported.")
            return
        if not self.slots.acquire(blocking=False):
            await reject(429, "Two uploads are already running. Please retry in a moment.", retry=True)
            return

        try:
            body = bytearray()
            try:
                async with asyncio.timeout(self.timeout):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > self.max_request:
                            raise _BodyTooLarge
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await reject(408, "Upload took too long. Please retry on a faster connection.")
                return
            except _BodyTooLarge:
                await reject(413, "Upload is too large. Use one image up to 8 MB.")
                return
            if declared is not None and declared != len(body):
                await reject(400, "The request length did not match the uploaded body.")
                return

            # The framework may ask again to watch for disconnects. Replay once,
            # then use the original receive channel without inventing messages.
            replayed = False

            async def replay() -> Message:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    data = bytes(body)
                    body.clear()
                    return {"type": "http.request", "body": data, "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        finally:
            self.slots.release()
