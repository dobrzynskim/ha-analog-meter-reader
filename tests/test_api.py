import asyncio

import pytest

from api import MeterReaderApiError, MeterReaderAuthError, async_ask_ai, async_fetch_snapshot


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


# --- Gemini (dostawca domyślny) -----------------------------------------


def test_async_ask_ai_gemini_parses_text_from_response():
    payload = {"candidates": [{"content": {"parts": [{"text": " 515.234 "}]}}]}
    session = FakeSession(FakeResponse(200, payload=payload))
    result = run(async_ask_ai(session, "gemini", "key", "gemini-2.5-flash", "prompt", b"jpeg"))
    assert result == "515.234"


def test_async_ask_ai_gemini_401_raises_auth_error():
    session = FakeSession(FakeResponse(401, payload={}))
    with pytest.raises(MeterReaderAuthError):
        run(async_ask_ai(session, "gemini", "bad-key", "gemini-2.5-flash", "prompt", b"jpeg"))


def test_async_ask_ai_gemini_400_raises_api_error():
    session = FakeSession(FakeResponse(400, text="bad request"))
    with pytest.raises(MeterReaderApiError):
        run(async_ask_ai(session, "gemini", "key", "gemini-2.5-flash", "prompt", b"jpeg"))


def test_async_ask_ai_gemini_error_body_included_in_message():
    """Regresja: błędy inne niż 400/401/403 (np. 404 przy wycofanym modelu)
    musiały być widoczne z treścią odpowiedzi Google, nie gołym kodem HTTP -
    bez tego zdiagnozowanie realnego problemu wymagało ręcznego curl."""
    session = FakeSession(
        FakeResponse(404, text='{"error": {"message": "model no longer available"}}')
    )
    with pytest.raises(MeterReaderApiError, match="model no longer available"):
        run(async_ask_ai(session, "gemini", "key", "gemini-2.5-flash", "prompt", b"jpeg"))


def test_async_ask_ai_gemini_malformed_shape_raises_api_error():
    session = FakeSession(FakeResponse(200, payload={"unexpected": True}))
    with pytest.raises(MeterReaderApiError):
        run(async_ask_ai(session, "gemini", "key", "gemini-2.5-flash", "prompt", b"jpeg"))


# --- Anthropic Claude -----------------------------------------------------


def test_async_ask_ai_anthropic_parses_text_from_response():
    payload = {"content": [{"type": "text", "text": " 515.234 "}]}
    session = FakeSession(FakeResponse(200, payload=payload))
    result = run(
        async_ask_ai(session, "anthropic", "key", "claude-sonnet-5", "prompt", b"jpeg")
    )
    assert result == "515.234"


def test_async_ask_ai_anthropic_401_raises_auth_error():
    session = FakeSession(FakeResponse(401, payload={}))
    with pytest.raises(MeterReaderAuthError):
        run(async_ask_ai(session, "anthropic", "bad-key", "claude-sonnet-5", "prompt", b"jpeg"))


def test_async_ask_ai_anthropic_malformed_shape_raises_api_error():
    session = FakeSession(FakeResponse(200, payload={"unexpected": True}))
    with pytest.raises(MeterReaderApiError):
        run(async_ask_ai(session, "anthropic", "key", "claude-sonnet-5", "prompt", b"jpeg"))


# --- Własne / OpenAI-compatible API ---------------------------------------


def test_async_ask_ai_openai_compatible_parses_text_from_response():
    payload = {"choices": [{"message": {"content": " 515.234 "}}]}
    session = FakeSession(FakeResponse(200, payload=payload))
    result = run(
        async_ask_ai(
            session,
            "openai_compatible",
            "key",
            "my-local-model",
            "prompt",
            b"jpeg",
            base_url="http://localhost:11434/v1",
        )
    )
    assert result == "515.234"


def test_async_ask_ai_openai_compatible_works_without_api_key():
    """Self-hosted serwery (Ollama, LM Studio...) często nie wymagają
    autoryzacji - pusty klucz nie powinien wysyłać złamanego nagłówka."""
    payload = {"choices": [{"message": {"content": "515.234"}}]}
    session = FakeSession(FakeResponse(200, payload=payload))
    result = run(
        async_ask_ai(
            session,
            "openai_compatible",
            "",
            "my-local-model",
            "prompt",
            b"jpeg",
            base_url="http://localhost:11434/v1",
        )
    )
    assert result == "515.234"


def test_async_ask_ai_openai_compatible_uses_default_base_url_when_missing():
    payload = {"choices": [{"message": {"content": "515.234"}}]}
    session = FakeSession(FakeResponse(200, payload=payload))
    result = run(
        async_ask_ai(session, "openai_compatible", "key", "gpt-4o", "prompt", b"jpeg")
    )
    assert result == "515.234"


def test_async_ask_ai_openai_compatible_401_raises_auth_error():
    session = FakeSession(FakeResponse(401, payload={}))
    with pytest.raises(MeterReaderAuthError):
        run(
            async_ask_ai(
                session,
                "openai_compatible",
                "bad-key",
                "gpt-4o",
                "prompt",
                b"jpeg",
                base_url="http://localhost:11434/v1",
            )
        )


def test_async_ask_ai_openai_compatible_malformed_shape_raises_api_error():
    session = FakeSession(FakeResponse(200, payload={"unexpected": True}))
    with pytest.raises(MeterReaderApiError):
        run(
            async_ask_ai(
                session,
                "openai_compatible",
                "key",
                "gpt-4o",
                "prompt",
                b"jpeg",
                base_url="http://localhost:11434/v1",
            )
        )
