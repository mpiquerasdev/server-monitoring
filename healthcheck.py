#!/usr/bin/env python3
"""Hourly public endpoint checks with transition alerts to one private chat."""

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


SERVICES = {
    "5Sitios": "https://www.5sitios.com/",
    "Reviok": "https://www.reviok.com/",
    "MyLifeManager": "https://mylife.freemyip.com/api/version",
    "TopNimbos Dashboard": "https://topnimbos-dashboard.freemyip.com/",
    "TopNimbos CRM": "https://topnimbos-mails.freemyip.com/crm",
    "VictorMur": "https://victormur-funnel.freemyip.com/paso1",
}
STATE_PATH = Path(os.environ.get("MONITOR_STATE_PATH", "/var/lib/server-monitoring/status.json"))


def send_message(message):
    token = os.environ["MONITOR_BOT_TOKEN"]
    chat_id = os.environ["MONITOR_CHAT_ID"]
    if not token or not chat_id or not chat_id.lstrip("-").isdigit():
        raise ValueError("Monitoring credentials are missing")
    endpoint = "https://api.telegram.org/bot" + token + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(endpoint, data=data), timeout=20) as response:
        if not json.load(response).get("ok"):
            raise RuntimeError("Telegram rejected health alert")


def probe(url):
    last_error = "unknown error"
    for attempt in range(2):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "server-monitoring/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                if 200 <= response.status < 400:
                    return True, "OK"
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc.reason if isinstance(exc, urllib.error.URLError) else exc)[:160]
        if attempt == 0:
            time.sleep(3)
    return False, last_error


def main():
    previous = {}
    if STATE_PATH.exists():
        previous = json.loads(STATE_PATH.read_text())
    current = dict(previous)
    for service, url in SERVICES.items():
        healthy, detail = probe(url)
        old = previous.get(service)
        if old is None:
            # First run establishes a baseline but still alerts on failures.
            if not healthy:
                send_message(f"🚨 CRÍTICO: {service} no responde\nURL: {url}\nError: {detail}")
        elif old != healthy:
            if healthy:
                send_message(f"✅ RECUPERADO: {service}\nURL: {url}")
            else:
                send_message(f"🚨 CRÍTICO: {service} no responde\nURL: {url}\nError: {detail}")
        current[service] = healthy
        print(f"{service}: {'healthy' if healthy else 'unhealthy'} ({detail})")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)


if __name__ == "__main__":
    main()
