#!/usr/bin/env python3
"""Small, dependency-free Telegram formatter and sender for private alerts."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request


MAX_MESSAGE_LENGTH = 3800  # Telegram permits 4096 characters after parsing.


def escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def compact(value: object, limit: int = 280) -> str:
    """Keep an operational detail useful, short, single-line and non-secret."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?i)\b(token|password|secret|api[_ -]?key)\s*([=:])\s*\S+", r"\1\2[oculto]", text)
    text = re.sub(r"https?://[^\s/@]+:[^\s/@]+@", "https://[credenciales]@", text)
    return text[:limit - 1].rstrip() + "…" if len(text) > limit else text


def _url_button(text: str, url: str) -> dict | None:
    return {"text": text, "url": url} if url.startswith(("https://", "http://")) else None


def send_message(token: str, chat_id: str, message: str, buttons: list[dict] | None = None) -> None:
    if not token or not chat_id or not chat_id.lstrip("-").isdigit():
        raise ValueError("Monitoring bot token or private chat ID is missing")
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    usable_buttons = [button for button in (buttons or []) if button]
    if usable_buttons:
        data["reply_markup"] = json.dumps({"inline_keyboard": [usable_buttons]}, separators=(",", ":"))
    endpoint = "https://api.telegram.org/bot" + token + "/sendMessage"
    encoded = urllib.parse.urlencode(data).encode()
    for attempt in range(5):
        request = urllib.request.Request(endpoint, data=encoded, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if not json.load(response).get("ok"):
                    raise RuntimeError("Telegram rejected monitoring notification")
            return
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise RuntimeError(f"Telegram notification failed with HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 4:
                raise RuntimeError(f"Telegram notification failed after five attempts: {exc}") from None
        time.sleep(min(2**attempt, 8))


def button(text: str, url: str) -> dict | None:
    return _url_button(text, url)
