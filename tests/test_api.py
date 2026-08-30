import asyncio

import pytest

from api import MeterReaderApiError, MeterReaderAuthError, async_ask_gemini, async_fetch_snapshot


class FakeResponse:
    def __init__(self, status, payload=None, body_bytes=None, text=""):
        self.status = status
        self._payload = payload
        self._body_bytes = body_bytes
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            import aiohttp

            raise aiohttp.ClientError(f"HTTP {self.status}")

    async def json(self, content_type=None):
        return self._payload

    async def read(self):
        return self._body_bytes

    async def text(self):
        return self._text


class FakeSession:
    def __init__(self, response):
        self._response = response

    def get(self, url, **kwargs):
        return self._response

    def post(self, url, **kwargs):
        return self._response


def run(coro):
    return asyncio.run(coro)


def test_async_fetch_snapshot_returns_bytes():
    session = FakeSession(FakeResponse(200, body_bytes=b"\xff\xd8\xff\xe0fakejpeg"))
    result = run(async_fetch_snapshot(session, "http://camera.local/snapshot"))
    assert result == b"\xff\xd8\xff\xe0fakejpeg"


def test_async_fetch_snapshot_error_status_raises():
    session = FakeSession(FakeResponse(500))
    with pytest.raises(MeterReaderApiError):
        run(async_fetch_snapshot(session, "http://camera.local/snapshot"))


def test_async_ask_gemini_parses_text_from_response():
    payload = {"candidates": [{"content": {"parts": [{"text": " 515.234 "}]}}]}
    session = FakeSession(FakeResponse(200, payload=payload))
    result = run(async_ask_gemini(session, "key", "gemini-2.5-flash", "prompt", b"jpeg"))
    assert result == "515.234"


def test_async_ask_gemini_401_raises_auth_error():
    session = FakeSession(FakeResponse(401, payload={}))
    with pytest.raises(MeterReaderAuthError):
        run(async_ask_gemini(session, "bad-key", "gemini-2.5-flash", "prompt", b"jpeg"))


def test_async_ask_gemini_400_raises_api_error():
    session = FakeSession(FakeResponse(400, text="bad request"))
    with pytest.raises(MeterReaderApiError):
        run(async_ask_gemini(session, "key", "gemini-2.5-flash", "prompt", b"jpeg"))


def test_async_ask_gemini_malformed_shape_raises_api_error():
    session = FakeSession(FakeResponse(200, payload={"unexpected": True}))
    with pytest.raises(MeterReaderApiError):
        run(async_ask_gemini(session, "key", "gemini-2.5-flash", "prompt", b"jpeg"))
