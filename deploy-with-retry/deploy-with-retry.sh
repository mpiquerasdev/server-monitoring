#!/usr/bin/env bash
# Retrying is deliberately narrow: source/configuration failures need attention,
# while the shared VPS can recover after another build releases disk pressure.
set -uo pipefail

[[ "$DEPLOY_MAX_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || { echo 'max-attempts must be a positive integer' >&2; exit 2; }
[[ "$DEPLOY_INITIAL_DELAY_SECONDS" =~ ^[1-9][0-9]*$ ]] || { echo 'initial-delay-seconds must be a positive integer' >&2; exit 2; }

is_transient_disk_pressure() {
  grep -Eqi 'less than [0-9]+ gib free|no space left on device|disk[^[:cntrl:]]*(full|space)|la build dejó menos de [0-9]+ gib libres|producción necesita al menos [0-9]+ gib libres' "$1"
}

for ((attempt = 1; attempt <= DEPLOY_MAX_ATTEMPTS; attempt++)); do
  log_file="$(mktemp)"
  trap 'rm -f "$log_file"' EXIT
  echo "Deployment attempt ${attempt}/${DEPLOY_MAX_ATTEMPTS}"
  set +e
  bash -o pipefail -c "$DEPLOY_COMMAND" 2>&1 | tee "$log_file"
  status=${PIPESTATUS[0]}
  set -e
  if [[ "$status" -eq 0 ]]; then
    echo "retry_count=$((attempt - 1))" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  if ! is_transient_disk_pressure "$log_file" || [[ "$attempt" -eq "$DEPLOY_MAX_ATTEMPTS" ]]; then
    exit "$status"
  fi
  delay=$((attempt * DEPLOY_INITIAL_DELAY_SECONDS))
  echo "Transient disk-pressure guard; retrying in ${delay}s"
  rm -f "$log_file"
  trap - EXIT
  sleep "$delay"
done
