#!/usr/bin/env bash
# Refresh completion hooks without restarting active GitHub Actions runners.
set -euo pipefail

for repo in 5sitios reviok mylifemanager topnimbos-dashboard topnimbos-crm victormur; do
  runner_dir="/opt/gh-runners/$repo"
  runner_home="/var/lib/gha-$repo"
  runner_user="gha-$repo"
  hook="/usr/local/libexec/gh-runner-$repo-job-completed.sh"
  if [ ! -d "$runner_dir" ] || ! id "$runner_user" >/dev/null 2>&1; then
    continue
  fi
  install -d -m 700 -o "$runner_user" -g "$runner_user" "$runner_home/dependency-manifest"
  cat > "$hook" <<HOOK
#!/usr/bin/env bash
set -euo pipefail
workspace='$runner_dir/_work/$repo'
/opt/server-monitoring/capture-dependency-manifest.sh '$repo' "\$workspace" '$runner_home/dependency-manifest' || true
if [ -d "\$workspace" ]; then
  find "\$workspace" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
fi
rm -f -- '$runner_home/.ssh/id_ed25519' '$runner_home/.ssh/known_hosts'
HOOK
  if [ "$repo" = "mylifemanager" ]; then
    printf '%s\n' 'rm -rf -- /tmp/mylifemanager-smoke-screenshots' >> "$hook"
  fi
  chmod 755 "$hook"
  chown root:root "$hook"
done
