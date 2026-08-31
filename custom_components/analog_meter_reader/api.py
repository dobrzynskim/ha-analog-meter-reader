"""HTTP klienci: pobranie zdjęcia z kamery + odczyt przez wybranego dostawcę AI.

Obsługiwani dostawcy (patrz const.AI_PROVIDER_*): Google Gemini, Anthropic
Claude, oraz dowolne API zgodne z OpenAI (obejmuje to zarówno sam OpenAI, jak
i self-hosted modele - Ollama, LM Studio, vLLM, text-generation-webui... -
czyli "swój model" użytkownika).
"""
from __future__ import annotations

import base64
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

TIMEOUT_SNAPSHOT_SECONDS = 10
TIMEOUT_AI_SECONDS = 30

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 1024

# Wartości dokładnie odpowiadające const.AI_PROVIDER_* - zdublowane jako
# zwykłe stringi (zamiast importu z .const), bo api.py celowo nie ma żadnych
# importów względnych (patrz tests/conftest.py - importowalne wprost, bez
# pakietu homeassistant/analog_meter_reader).
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"


class MeterReaderApiError(Exception):
    """Błąd komunikacji z kamerą lub API AI."""


class MeterReaderAuthError(MeterReaderApiError):
    """Nieprawidłowy klucz API."""


async def async_fetch_snapshot(session: aiohttp.ClientSession, url: str) -> bytes:
    """Pobiera pojedyncze zdjęcie ze snapshotu kamery IP."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SNAPSHOT_SECONDS)
        ) as resp:
            resp.raise_for_status()
            return await resp.read()
    except aiohttp.ClientError as err:
        raise MeterReaderApiError(f"Nie udało się pobrać zdjęcia z kamery: {err}") from err


async def async_ask_ai(
    session: aiohttp.ClientSession,
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    image_bytes: bytes,
    base_url: str | None = None,
) -> str:
    """Wysyła przycięty fragment zdjęcia do wybranego dostawcy AI, zwraca surowy tekst odpowiedzi."""
    if provider == PROVIDER_ANTHROPIC:
        return await _async_ask_anthropic(session, api_key, model, prompt, image_bytes)
    if provider == PROVIDER_OPENAI_COMPATIBLE:
        return await _async_ask_openai_compatible(
            session, base_url or DEFAULT_OPENAI_COMPATIBLE_BASE_URL, api_key, model, prompt, image_bytes
        )
    return await _async_ask_gemini(session, api_key, model, prompt, image_bytes)


async def _async_ask_gemini(
    session: aiohttp.ClientSession, api_key: str, model: str, prompt: str, image_bytes: bytes
) -> str:
    """Wysyła zapytanie do Gemini Vision."""
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0},
    }
    url = GEMINI_URL.format(model=model)
    try:
        async with session.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_AI_SECONDS),
        ) as resp:
            if resp.status >= 400:
                # Zawsze czytamy treść błędu - Google zwraca tam konkretny powód
                # (np. "model X no longer available", limit wyczerpany, zły
                # klucz), bez którego zostaje tylko goły kod HTTP nie do
                # zdiagnozowania z samego statusu.
                body = await resp.text()
                if resp.status in (401, 403):
                    raise MeterReaderAuthError(
                        f"Nieprawidłowy klucz API Gemini (HTTP {resp.status}): {body}"
                    )
                raise MeterReaderApiError(f"Gemini zwróciło błąd (HTTP {resp.status}): {body}")
            data = await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise MeterReaderApiError(f"Błąd połączenia z Gemini: {err}") from err

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as err:
        raise MeterReaderApiError(f"Nieoczekiwana odpowiedź Gemini: {data}") from err


async def _async_ask_anthropic(
    session: aiohttp.ClientSession, api_key: str, model: str, prompt: str, image_bytes: bytes
) -> str:
    """Wysyła zapytanie do Claude (Anthropic Messages API, vision)."""
    payload = {
        "model": model,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        async with session.post(
            ANTHROPIC_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_AI_SECONDS),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                if resp.status in (401, 403):
                    raise MeterReaderAuthError(
                        f"Nieprawidłowy klucz API Claude (HTTP {resp.status}): {body}"
                    )
                raise MeterReaderApiError(f"Claude zwróciło błąd (HTTP {resp.status}): {body}")
            data = await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise MeterReaderApiError(f"Błąd połączenia z Claude: {err}") from err

    try:
        return data["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as err:
        raise MeterReaderApiError(f"Nieoczekiwana odpowiedź Claude: {data}") from err


async def _async_ask_openai_compatible(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    image_bytes: bytes,
) -> str:
    """Wysyła zapytanie do dowolnego API zgodnego z OpenAI Chat Completions.

    Obejmuje to zarówno sam OpenAI, jak i self-hosted modele (Ollama, LM
    Studio, vLLM, text-generation-webui...) wystawiające ten sam format
    zapytania. api_key bywa opcjonalny dla self-hosted serwerów bez
    autoryzacji - wtedy po prostu nie dołączamy nagłówka Authorization."""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                        },
                    },
                ],
            }
        ],
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{base_url.rstrip('/')}/chat/completions"
    try:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_AI_SECONDS),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                if resp.status in (401, 403):
                    raise MeterReaderAuthError(
                        f"Nieprawidłowy klucz API ({base_url}, HTTP {resp.status}): {body}"
                    )
                raise MeterReaderApiError(f"API ({base_url}) zwróciło błąd (HTTP {resp.status}): {body}")
            data = await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise MeterReaderApiError(f"Błąd połączenia z {base_url}: {err}") from err

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as err:
        raise MeterReaderApiError(f"Nieoczekiwana odpowiedź z {base_url}: {data}") from err
