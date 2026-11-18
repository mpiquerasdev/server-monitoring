#!/usr/bin/env bash
# Must run while /run/lock/gh-ci-build.lock is held by the caller.
# It preserves live containers, their images and all volumes.
set -euo pipefail

minimum_gib="${BUILD_MIN_FREE_GIB:-12}"
[[ "$minimum_gib" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_MIN_FREE_GIB must be a positive integer' >&2; exit 2; }

available_gib() {
  df -BG --output=avail / | tail -n 1 | tr -dc '0-9'
}

available="$(available_gib)"
if (( available < minimum_gib )); then
  echo "Disk preflight: ${available} GiB free; reclaiming unused Docker build cache"
  docker buildx prune --all --force --min-free-space "${minimum_gib}GB" --reserved-space 1GB
  # These commands cannot remove a running container, its image or a volume.
  docker container prune --force --filter 'until=24h'
  # A failed build can leave a brand-new, unreferenced image. Do not retain it
  # for 24 hours: Docker guarantees image prune never removes an image used by
  # any container, including the previous production container kept for rollback.
  docker image prune --all --force
  # Some tagged Compose build results remain after image prune even with zero
  # container references. Remove only those exact images, without --force; a
  # referenced image or a parent layer Docker still needs will be retained.
  while IFS= read -r image_id; do
    [[ -n "$image_id" ]] || continue
    if [[ -z "$(docker ps --all --quiet --filter "ancestor=$image_id")" ]]; then
      docker image rm "$image_id" || true
    fi
  done < <(docker image ls --quiet --no-trunc | sort -u)
  docker network prune --force --filter 'until=24h'
  available="$(available_gib)"
fi

if (( available < minimum_gib )); then
  echo "Less than ${minimum_gib} GiB free after safe cleanup; live services untouched" >&2
  exit 75
fi

echo "Disk preflight passed: ${available} GiB free (minimum ${minimum_gib} GiB)"
exec "$@"
