"""Thin wrapper around the Sarvam REST APIs used by gradebot.

Two endpoints only:
  * POST /speech-to-text          -> transcribe a short (<=30s) clip
  * POST /v2/chat/completions     -> Sarvam / open-weight chat models, incl. image input
"""
from __future__ import annotations

import json
from typing import Any

import requests

from config import SARVAM_API_KEY, SARVAM_BASE_URL


class SarvamError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not SARVAM_API_KEY:
        raise SarvamError(
            "SARVAM_API_KEY is not set. Export it (see .env.example) before running with --brain sarvam."
        )
    return {"api-subscription-key": SARVAM_API_KEY}


def transcribe_file(path: str, model: str, mode: str = "transcribe",
                    language_code: str | None = None) -> dict[str, Any]:
    """POST /speech-to-text. Returns {'transcript': ..., 'language_code': ...}."""
    data: dict[str, str] = {"model": model, "mode": mode}
    if language_code:
        data["language_code"] = language_code
    with open(path, "rb") as fh:
        files = {"file": (path.split("/")[-1], fh)}
        resp = requests.post(
            f"{SARVAM_BASE_URL}/speech-to-text",
            headers=_headers(),
            data=data,
            files=files,
            timeout=120,
        )
    if resp.status_code == 422:
        raise SarvamError(
            f"'{path}' was rejected (422). The sync REST API only accepts clips up to 30 seconds. "
            "Split the recording into <=30s clips, or use the Batch API for long audio."
        )
    if resp.status_code >= 400:
        raise SarvamError(f"Speech-to-text failed ({resp.status_code}): {resp.text[:400]}")
    return resp.json()


def chat(messages: list[dict[str, Any]], model: str, temperature: float = 0.2,
         max_tokens: int = 2048) -> str:
    """POST /v2/chat/completions. Returns the assistant's text content."""
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(
        f"{SARVAM_BASE_URL}/v2/chat/completions",
        headers={**_headers(), "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=300,
    )
    if resp.status_code >= 400:
        raise SarvamError(f"Chat completion failed ({resp.status_code}): {resp.text[:400]}")
    payload = resp.json()
    return payload["choices"][0]["message"]["content"]
