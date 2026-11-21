#!/usr/bin/env bash
# Must run while /run/lock/gh-ci-build.lock is held by the caller.
# It preserves live containers, their images and all volumes.
set -euo pipefail

minimum_gib="${BUILD_MIN_FREE_GIB:-12}"
[[ "$minimum_gib" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_MIN_FREE_GIB must be a positive integer' >&2; exit 2; }
minimum_memory_gib="${BUILD_MIN_AVAILABLE_MEMORY_GIB:-3}"
[[ "$minimum_memory_gib" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_MIN_AVAILABLE_MEMORY_GIB must be a positive integer' >&2; exit 2; }

available_gib() {
  df -BG --output=avail / | tail -n 1 | tr -dc '0-9'
}

available="$(available_gib)"
if (( available < minimum_gib )); then
  echo "Disk preflight: ${available} GiB free; reclaiming unused Docker build cache"
  docker buildx prune --all --force --min-free-space "${minimum_gib}GB" --reserved-space 1GB
  # These commands cannot remove a running container, its image or a volume.
  docker container prune --force --filter 'until=24h'
  # Keep tagged release candidates loaded before this preflight. They may not
  # have a container reference until the rollout starts.
  docker image prune --force
  docker network prune --force --filter 'until=24h'
  available="$(available_gib)"
fi

if (( available < minimum_gib )); then
  echo "Less than ${minimum_gib} GiB free after safe cleanup; live services untouched" >&2
  exit 75
fi

available_memory_kib="$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)"
if (( available_memory_kib < minimum_memory_gib * 1024 * 1024 )); then
  echo "Memory preflight: less than ${minimum_memory_gib} GiB available; live services untouched" >&2
  exit 75
fi

echo "Disk preflight passed: ${available} GiB free (minimum ${minimum_gib} GiB)"
exec "$@"
