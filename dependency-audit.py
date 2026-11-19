#!/usr/bin/env python3
"""Daily, read-only dependency and VPS update summary for the private bot.

Dependency manifests are copied by each self-hosted runner's completion hook
before its disposable checkout is removed. This avoids installing project
dependencies or touching a production checkout merely to audit it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from telegram import button, compact, escape, send_message


REPOSITORIES = {
    "5sitios": "5Sitios",
    "reviok": "Reviok",
    "mylifemanager": "My Life Manager",
    "topnimbos-dashboard": "TopNimbos Dashboard",
    "topnimbos-crm": "TopNimbos CRM",
    "victormur": "VictorMur",
}
MANIFEST_ROOT = Path(
    os.environ.get("DEPENDENCY_AUDIT_MANIFEST_ROOT", "/var/lib")
)
STATE_PATH = Path(
    os.environ.get(
        "DEPENDENCY_AUDIT_STATE_PATH",
        "/var/lib/server-monitoring/dependency-audit.json",
    )
)
OSV_URL = "https://api.osv.dev/v1/querybatch"
MAX_QUERIES_PER_BATCH = 500


def run(command: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"error: {error}"
    return result.stdout if result.returncode == 0 else f"error: {compact(result.stderr or result.stdout, 160)}"


def npm_packages(path: Path) -> set[tuple[str, str, str]]:
    try:
        lock = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    packages = set()
    for location, item in (lock.get("packages") or {}).items():
        if not location.startswith("node_modules/") or not isinstance(item, dict):
            continue
        name, version = item.get("name"), item.get("version")
        if not name:
            name = location.removeprefix("node_modules/").rsplit("node_modules/", 1)[-1]
        if isinstance(name, str) and isinstance(version, str) and version and not version.startswith(("file:", "git+", "http:")):
            packages.add(("npm", name, version))
    # npm lockfile v1 does not have the packages map. Nested dependencies are
    # intentionally walked so audit coverage is not limited to direct deps.
    def add_v1(items):
        for name, item in (items or {}).items():
            if not isinstance(item, dict):
                continue
            version = item.get("version")
            if isinstance(version, str) and version and not version.startswith(("file:", "git+", "http:")):
                packages.add(("npm", name, version))
            add_v1(item.get("dependencies"))

    if not packages:
        add_v1(lock.get("dependencies"))
    return packages


REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.+!:-]+)")


def python_packages(path: Path) -> set[tuple[str, str, str]]:
    packages = set()
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return packages
    for line in lines:
        match = REQUIREMENT.match(line.split("#", 1)[0])
        if match:
            packages.add(("PyPI", match.group(1), match.group(2)))
    return packages


def find_packages(manifest_dir: Path) -> set[tuple[str, str, str]]:
    packages = set()
    for lock in manifest_dir.rglob("package-lock*.json"):
        packages.update(npm_packages(lock))
    for requirements in manifest_dir.rglob("requirements*.txt"):
        packages.update(python_packages(requirements))
    return packages


def severity(vulnerability: dict) -> str:
    database = vulnerability.get("database_specific") or {}
    value = str(database.get("severity", "")).lower()
    if value in {"critical", "high", "medium", "moderate", "low"}:
        return "medium" if value == "moderate" else value
    for entry in vulnerability.get("severity") or []:
        match = re.search(r"(?:CVSS:[^/]+/)?AV:[^ ]+", str(entry.get("score", "")))
        if match:
            # CVSS vectors cannot be safely ranked without a parser. Unknown is
            # more honest than inventing a severity from a textual vector.
            return "unknown"
    return "unknown"


def osv(packages: set[tuple[str, str, str]]) -> tuple[dict[tuple[str, str, str], list[dict]], str | None]:
    results = {}
    ordered = sorted(packages)
    try:
        for start in range(0, len(ordered), MAX_QUERIES_PER_BATCH):
            batch = ordered[start : start + MAX_QUERIES_PER_BATCH]
            payload = json.dumps(
                {
                    "queries": [
                        {"package": {"ecosystem": ecosystem, "name": name}, "version": version}
                        for ecosystem, name, version in batch
                    ]
                }
            ).encode()
            request = urllib.request.Request(
                OSV_URL,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "server-monitoring/1.0"},
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                response_data = json.load(response).get("results", [])
            if len(response_data) != len(batch):
                raise RuntimeError("OSV returned an incomplete batch")
            for package, result in zip(batch, response_data):
                results[package] = result.get("vulns") or []
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as error:
        return {}, compact(error, 180)
    return results, None


def apt_updates() -> tuple[int | None, str | None]:
    output = run(["apt-get", "-s", "upgrade"], timeout=90)
    if output.startswith("error:"):
        return None, output.removeprefix("error: ")
    return len(re.findall(r"^Inst\s+", output, flags=re.MULTILINE)), None


def disk_detail() -> str:
    output = run(["df", "-h", "/"], timeout=10)
    if output.startswith("error:"):
        return output.removeprefix("error: ")
    return output.splitlines()[-1] if len(output.splitlines()) > 1 else output


def audit_repository(repo: str, label: str) -> dict:
    manifest_dir = MANIFEST_ROOT / f"gha-{repo}" / "dependency-manifest"
    packages = find_packages(manifest_dir)
    if not packages:
        return {"repo": repo, "label": label, "status": "missing", "packages": 0, "vulnerabilities": []}
    response, error = osv(packages)
    if error:
        return {"repo": repo, "label": label, "status": "error", "packages": len(packages), "error": error, "vulnerabilities": []}
    vulnerabilities = []
    for package, items in response.items():
        for item in items:
            vulnerabilities.append(
                {
                    "package": f"{package[1]}@{package[2]}",
                    "id": item.get("id", "OSV"),
                    "severity": severity(item),
                    "summary": compact(item.get("summary", "Sin resumen"), 110),
                }
            )
    return {"repo": repo, "label": label, "status": "ok", "packages": len(packages), "vulnerabilities": vulnerabilities}


def audit_all():
    return [audit_repository(repo, label) for repo, label in REPOSITORIES.items()]


def report(reports: list[dict], updates: int | None, update_error: str | None) -> str:
    counts = {name: 0 for name in ("critical", "high", "medium", "low", "unknown")}
    for item in reports:
        for vulnerability in item["vulnerabilities"]:
            counts[vulnerability["severity"]] += 1
    scanned = sum(item["status"] == "ok" for item in reports)
    headline = f"🔐 <b>DEPENDENCIAS · {time.strftime('%d %b · %H:%M')}</b>"
    totals = (
        f"🚨 Críticas: <b>{counts['critical']}</b> · "
        f"⚠️ Altas: <b>{counts['high']}</b> · "
        f"• Medias: <b>{counts['medium']}</b> · "
        f"◦ Bajas: <b>{counts['low']}</b>"
    )
    if counts["unknown"]:
        totals += f" · ❔ Sin clasificar: <b>{counts['unknown']}</b>"
    server = f"Servidor: {updates} actualizaciones APT pendientes" if updates is not None else f"Servidor: no se pudo consultar APT ({escape(update_error)})"
    details = []
    for item in reports:
        if item["status"] == "missing":
            details.append(f"⚪ {escape(item['label'])}: manifiesto pendiente")
        elif item["status"] == "error":
            details.append(f"❓ {escape(item['label'])}: consulta no disponible ({escape(item['error'])})")
        elif not item["vulnerabilities"]:
            details.append(f"✅ {escape(item['label'])}: {item['packages']} paquetes")
        else:
            priorities = ", ".join(
                f"{escape(v['package'])} ({escape(v['severity'])})" for v in item["vulnerabilities"][:4]
            )
            remaining = len(item["vulnerabilities"]) - 4
            details.append(f"⚠️ {escape(item['label'])}: {len(item['vulnerabilities'])} · {priorities}{f' +{remaining}' if remaining else ''}")
    details.append(f"Disco: {escape(disk_detail())}")
    return f"{headline}\n{totals}\n{scanned}/{len(reports)} proyectos auditados\n<b>{server}</b>\n<blockquote expandable>{'<br>'.join(details)}</blockquote>"


def main():
    reports = audit_all()
    updates, update_error = apt_updates()
    payload = {"checked_at": int(time.time()), "reports": reports, "apt_updates": updates, "apt_error": update_error}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)
    token = os.environ["MONITOR_BOT_TOKEN"]
    chat_id = os.environ["MONITOR_CHAT_ID"]
    send_message(token, chat_id, report(reports, updates, update_error), [button("📦 Seguridad GitHub", "https://github.com/mpiquerasdev?tab=repositories")])


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert npm_packages(Path(__file__).parent / "test-fixtures-does-not-exist") == set()
        assert python_packages(Path(__file__).parent / "test-fixtures-does-not-exist") == set()
        sample = report(
            [
                {
                    "label": "Smoke",
                    "status": "ok",
                    "packages": 1,
                    "vulnerabilities": [
                        {"package": "sample@1", "severity": "critical"},
                        {"package": "sample@2", "severity": "high"},
                        {"package": "sample@3", "severity": "medium"},
                        {"package": "sample@4", "severity": "low"},
                    ],
                }
            ],
            0,
            None,
        )
        assert all(level in sample for level in ("Críticas: <b>1</b>", "Altas: <b>1</b>", "Medias: <b>1</b>", "Bajas: <b>1</b>"))
        print("Dependency audit helpers: OK")
    else:
        main()
