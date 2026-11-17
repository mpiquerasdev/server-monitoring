#!/usr/bin/env bash
set -euo pipefail

exec 9>/run/lock/server-monitoring-docker-cleanup.lock
flock -n 9 || exit 0

# A build needs its cache and rollback images until it has finished. Try again
# at the next daily run if a deployment is active.
if pgrep -af 'docker compose .* (build|up)' | grep -v -E '(pgrep|docker-cleanup.sh)' >/dev/null; then
  echo 'Docker deployment active; cleanup postponed'
  exit 0
fi

before_volumes=$(docker volume ls -q | sort)
docker container prune --force --filter 'until=72h'
docker image prune --all --force --filter 'until=72h'
docker network prune --force --filter 'until=72h'
docker buildx prune --force --max-used-space 6GB --min-free-space 8GB --reserved-space 2GB
after_volumes=$(docker volume ls -q | sort)
if [[ "$before_volumes" != "$after_volumes" ]]; then
  echo 'Docker volume list changed unexpectedly during cleanup' >&2
  exit 1
fi
df -h /
docker system df
