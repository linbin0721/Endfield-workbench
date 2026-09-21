"""Bound recognition uploads before Starlette's multipart parser reads them."""

import asyncio
import json
import time
from typing import Any


MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_MULTIPART_BYTES = MAX_IMAGE_BYTES + 64 * 1024
MAX_UPLOAD_SECONDS = 30.0


class LimitedRecognitionUpload:
    def __init__(self, app: Any, max_uploads: int):
        self.app = app
        self._slots = asyncio.Semaphore(max_uploads)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/v1/puzzles/balloon/recognize":
            await self.app(scope, receive, send)
            return
        if self._slots.locked():
            await self._reject(send, 429, "UPLOAD_BUSY", "同时上传的图片过多，请稍后重试")
            return
        await self._slots.acquire()
        try:
            body = bytearray()
            deadline = time.monotonic() + MAX_UPLOAD_SECONDS
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._reject(send, 408, "UPLOAD_TIMEOUT", "图片上传超时，请重试")
                    return
                try:
                    message = await asyncio.wait_for(receive(), timeout=remaining)
                except asyncio.TimeoutError:
                    await self._reject(send, 408, "UPLOAD_TIMEOUT", "图片上传超时，请重试")
                    return
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_MULTIPART_BYTES:
                    await self._reject(send, 413, "UPLOAD_TOO_LARGE", "图片不能超过 12 MB")
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay() -> dict:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return {"type": "http.disconnect"}

            await self.app(scope, replay, send)
        finally:
            self._slots.release()

    @staticmethod
    async def _reject(send: Any, status: int, code: str, message: str) -> None:
        body = json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())
        ]
        if status == 429:
            headers.append((b"retry-after", b"5"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
