#!/usr/bin/env python3
"""Hourly public endpoint checks with transition alerts to one private chat."""

import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from telegram import button, compact, escape, send_message as telegram_send_message


SERVICES = {
    "5Sitios": "https://www.5sitios.com/",
    "Reviok": "https://www.reviok.com/",
    "MyLifeManager": "https://mylife.freemyip.com/api/version",
    "TopNimbos Dashboard": "https://topnimbos-dashboard.freemyip.com/",
    "TopNimbos CRM": "https://topnimbos-mails.freemyip.com/crm",
    "VictorMur": "https://victormur-funnel.freemyip.com/paso1",
}
STATE_PATH = Path(os.environ.get("MONITOR_STATE_PATH", "/var/lib/server-monitoring/status.json"))


def send_message(message, buttons=None):
    token = os.environ["MONITOR_BOT_TOKEN"]
    chat_id = os.environ["MONITOR_CHAT_ID"]
    if not token or not chat_id or not chat_id.lstrip("-").isdigit():
        raise ValueError("Monitoring credentials are missing")
    telegram_send_message(token, chat_id, message, buttons)


def service_alert(service, url, detail=None, recovered=False):
    state = "✅ <b>Recuperado</b>" if recovered else "🚨 <b>No responde</b>"
    message = f"<b>SALUD · {escape(service)}</b>\n{state}"
    if detail:
        message += f"\n<b>Motivo:</b> {escape(compact(detail, 220))}"
    message += f"\n<blockquote expandable>URL: {escape(url)}\nSonda pública: 2 intentos</blockquote>"
    return message


def runner_alert(service, unit, recovered=False):
    state = "✅ <b>Recuperado</b>" if recovered else "🚨 <b>Runner inactivo</b>"
    return (
        f"<b>RUNNER · {escape(service)}</b>\n{state}"
        f"\n<blockquote expandable>Unidad: <code>{escape(unit)}</code>\n"
        f"Diagnóstico: <code>journalctl -u {escape(unit)}</code></blockquote>"
    )


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
                send_message(service_alert(service, url, detail), [button("🌐 Abrir servicio", url)])
        elif old != healthy:
            if healthy:
                send_message(service_alert(service, url, recovered=True), [button("🌐 Abrir servicio", url)])
            else:
                send_message(service_alert(service, url, detail), [button("🌐 Abrir servicio", url)])
        current[service] = healthy
        print(f"{service}: {'healthy' if healthy else 'unhealthy'} ({detail})")
    for unit_file in sorted(Path('/etc/systemd/system').glob('gh-runner-*.service')):
        unit = unit_file.name
        service = f"Runner {unit.removeprefix('gh-runner-').removesuffix('.service')}"
        result = subprocess.run(
            ['systemctl', 'is-active', '--quiet', unit],
            check=False, timeout=10,
        )
        healthy = result.returncode == 0
        old = previous.get(service)
        if (old is None and not healthy) or (old is not None and old != healthy):
            if healthy:
                send_message(runner_alert(service, unit, recovered=True))
            else:
                send_message(runner_alert(service, unit))
        current[service] = healthy
        print(f"{service}: {'healthy' if healthy else 'unhealthy'}")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)


if __name__ == "__main__":
    main()
