#!/usr/bin/env bash
# Copy only dependency metadata before a runner destroys its disposable checkout.
# No source, environment file or credential is retained.
set -euo pipefail

repo=${1:?repository name required}
workspace=${2:?workspace path required}
target=${3:?target path required}

case "$target" in
  /var/lib/gha-*/dependency-manifest) ;;
  *) echo "Unexpected dependency manifest destination" >&2; exit 2 ;;
esac
rm -rf -- "$target"
install -d -m 700 "$target"
for pattern in package.json package-lock.json npm-shrinkwrap.json requirements.txt requirements-*.txt pyproject.toml poetry.lock Pipfile.lock; do
  while IFS= read -r -d '' manifest; do
    relative=${manifest#"$workspace"/}
    install -d -m 700 "$target/$(dirname "$relative")"
    install -m 600 "$manifest" "$target/$relative"
  done < <(find "$workspace" -maxdepth 3 -type f -name "$pattern" -print0 2>/dev/null)
done
printf '%s\n' "$repo" > "$target/repository"
