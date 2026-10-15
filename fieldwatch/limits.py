"""Bound all analysis POST bodies before parsing, with cancellation-safe admission."""
import asyncio
from threading import BoundedSemaphore
from starlette.responses import JSONResponse

MAX_BODY = 49 * 1024 * 1024


class RequestLimits:
    def __init__(self, app, max_body=MAX_BODY, timeout=30):
        self.app, self.max_body, self.timeout = app, max_body, timeout
        self.slots = BoundedSemaphore(2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        async def reject(code, message):
            await JSONResponse({"detail":message}, code, headers={"X-Content-Type-Options":"nosniff", "Cache-Control":"no-store"})(scope, receive, send)
        headers = scope.get("headers", [])
        lengths = [v for k,v in headers if k == b"content-length"]
        if lengths and (len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 20 or any(k == b"transfer-encoding" for k,v in headers)):
            return await reject(400, "Invalid request length.")
        if lengths and int(lengths[0]) > self.max_body:
            return await reject(413, "Request exceeds 49 MiB.")
        if any(k == b"content-encoding" and v.lower() != b"identity" for k,v in headers):
            return await reject(415, "Compressed requests are not accepted.")
        if not self.slots.acquire(blocking=False):
            return await reject(429, "Two jobs are already active. Retry shortly.")
        try:
            body = bytearray()
            try:
                async with asyncio.timeout(self.timeout):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > self.max_body:
                            return await reject(413, "Request exceeds 49 MiB.")
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "Upload timed out.")
            if lengths and int(lengths[0]) != len(body):
                return await reject(400, "Request length mismatch.")
            replayed = False
            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    data = bytes(body)
                    body.clear()
                    return {"type":"http.request", "body":data, "more_body":False}
                return await receive()
            await self.app(scope, replay, send)
        finally:
            self.slots.release()
