#!/usr/bin/env python3
"""Send one deployment result to a fixed, private Telegram chat."""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def main():
    token = os.environ["MONITOR_BOT_TOKEN"]
    chat_id = os.environ["MONITOR_CHAT_ID"]
    service = os.environ["MONITOR_SERVICE"]
    url = os.environ["MONITOR_URL"]
    result = os.environ["MONITOR_RESULT"]
    run_url = os.environ["MONITOR_RUN_URL"]
    if not token or not chat_id or not chat_id.lstrip("-").isdigit():
        raise ValueError("Monitoring bot token or private chat ID is missing")
    if result == "success":
        label = "✅ Despliegue completado"
    elif result == "cancelled":
        label = "⚠️ Despliegue cancelado"
    else:
        label = "🚨 Despliegue fallido"
    started_at = int(os.environ["MONITOR_STARTED_AT"])
    elapsed = max(0, int(time.time()) - started_at)
    message = (
        f"{label}: {service}\n"
        f"Tiempo: {elapsed // 60} min {elapsed % 60} s ({elapsed} s)\n"
        f"Web: {url}\n"
        f"Detalles: {run_url}"
    )
    endpoint = "https://api.telegram.org/bot" + token + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode()
    request = urllib.request.Request(endpoint, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        if not payload.get("ok"):
            raise RuntimeError("Telegram rejected deployment notification")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Telegram notification failed with HTTP {exc.code}") from None
    print(f"Deployment notification delivered for {service} ({result}, {elapsed} s)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(f"Monitoring error: {exc}", file=sys.stderr)
        sys.exit(1)
