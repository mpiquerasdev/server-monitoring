#!/usr/bin/env python3
"""Send one deployment result to a fixed, private Telegram chat."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from telegram import button, compact, escape, send_message


def failure_reason() -> str:
    """Read this job's log and return the last actionable failure, never a secret."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    job_name = os.environ.get("GITHUB_JOB", "")
    if not all((token, repository, run_id, job_name)):
        return "No se pudo obtener el motivo automático. Abre el workflow."
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    try:
        jobs_request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100", headers=headers
        )
        with urllib.request.urlopen(jobs_request, timeout=15) as response:
            jobs = json.load(response).get("jobs", [])
        job = next((item for item in jobs if item.get("name") == job_name), None)
        if not job:
            return "El job falló antes de poder identificar el paso."
        log_request = urllib.request.Request(job["logs_url"], headers=headers)
        with urllib.request.urlopen(log_request, timeout=25) as response:
            log = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError):
        return "El workflow falló; abre el detalle para ver el paso afectado."

    lines = [compact(line, 360) for line in log.splitlines()]
    lines = [re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s+", "", line) for line in lines]
    actionable = (
        r"less than \d+ gib free|no space left|disk.*(full|space)|out of memory|"
        r"health(check)? .*fail|unhealthy|connection refused|timed out|"
        r"permission denied|authentication failed|could not recover|missing|required|"
        r"make: \*\*\*|docker.*error|error response from daemon"
    )
    for line in reversed(lines):
        if re.search(actionable, line, re.IGNORECASE):
            return line
    for line in reversed(lines):
        if re.search(r"terminated|killed", line, re.IGNORECASE):
            return "El despliegue se interrumpió durante la compilación; producción no se sustituyó."
    return "El workflow falló; abre el detalle para ver el paso afectado."


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
        status = "✅ <b>Publicado</b>"
    elif result == "cancelled":
        status = "⚠️ <b>Cancelado</b>"
    else:
        status = "❌ <b>Falló</b>"
    started_at = int(os.environ["MONITOR_STARTED_AT"])
    elapsed = max(0, int(time.time()) - started_at)
    metadata = [f"⏱ {elapsed // 60} min {elapsed % 60} s"]
    ref = os.environ.get("GITHUB_REF_NAME", "")
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    if ref and sha:
        metadata.append(f"<code>{escape(ref)} · {escape(sha)}</code>")
    message = f"<b>DEPLOY · {escape(service)}</b>\n{status} · {' · '.join(metadata)}"
    if result not in ("success", "cancelled"):
        message += f"\n<b>Motivo:</b> {escape(failure_reason())}"
    message += "\n<blockquote expandable>" + "\n".join(
        (f"Servicio: {escape(service)}", f"Resultado: {escape(result)}", f"Web: {escape(url)}", f"Workflow: {escape(run_url)}")
    ) + "</blockquote>"
    send_message(token, chat_id, message, [button("🌐 Abrir web", url), button("⚙️ Ver workflow", run_url)])
    print(f"Deployment notification delivered for {service} ({result}, {elapsed} s)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(f"Monitoring error: {exc}", file=sys.stderr)
        sys.exit(1)
