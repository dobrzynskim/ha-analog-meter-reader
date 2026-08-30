"""HTTP klienci: pobranie zdjęcia z kamery + odczyt przez Gemini Vision."""
from __future__ import annotations

import base64
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

TIMEOUT_SNAPSHOT_SECONDS = 10
TIMEOUT_GEMINI_SECONDS = 30

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


async def async_ask_gemini(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    prompt: str,
    image_bytes: bytes,
) -> str:
    """Wysyła przycięty fragment zdjęcia do Gemini Vision, zwraca surowy tekst odpowiedzi."""
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
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_GEMINI_SECONDS),
        ) as resp:
            if resp.status in (401, 403):
                raise MeterReaderAuthError(f"Nieprawidłowy klucz API Gemini (HTTP {resp.status})")
            if resp.status == 400:
                raise MeterReaderApiError(f"Gemini odrzuciło zapytanie (400): {await resp.text()}")
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise MeterReaderApiError(f"Błąd połączenia z Gemini: {err}") from err

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as err:
        raise MeterReaderApiError(f"Nieoczekiwana odpowiedź Gemini: {data}") from err
