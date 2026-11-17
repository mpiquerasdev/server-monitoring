#!/usr/bin/env bash
# Install one repository-scoped GitHub Actions runner. Read its short-lived
# registration token from stdin; never put the token on a command line.
set -euo pipefail

repo=${1:?repository name required}
case "$repo" in
  5sitios|reviok|mylifemanager|topnimbos-dashboard|topnimbos-crm|victormur) ;;
  *) echo 'Unknown repository' >&2; exit 2 ;;
esac
IFS= read -r registration_token
test -n "$registration_token"

runner_version=2.338.2
runner_sha256=baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40
runner_user="gha-${repo}"
runner_dir="/opt/gh-runners/${repo}"
runner_home="/var/lib/${runner_user}"
service="gh-runner-${repo}.service"
runner_url="https://github.com/mpiquerasdev/${repo}"
runner_name="vps-5sitios-${repo}"
cleanup_hook="/usr/local/libexec/gh-runner-${repo}-job-completed.sh"
memory_limit=3G
if [ "$repo" = mylifemanager ] || [ "$repo" = 5sitios ]; then
  memory_limit=3500M
fi

printf 'f /run/lock/gh-ci-build.lock 0666 root root -\n' > /etc/tmpfiles.d/gh-ci-build.conf
systemd-tmpfiles --create /etc/tmpfiles.d/gh-ci-build.conf

if ! id "$runner_user" >/dev/null 2>&1; then
  useradd --system --user-group --create-home --home-dir "$runner_home" --shell /usr/sbin/nologin "$runner_user"
fi
install -d -m 700 -o "$runner_user" -g "$runner_user" "$runner_home" "$runner_dir"
if [ ! -x "$runner_dir/config.sh" ]; then
  archive=$(mktemp /tmp/actions-runner.XXXXXXXX.tar.gz)
  trap 'rm -f "$archive"' EXIT
  curl -fsSL --retry 3 \
    "https://github.com/actions/runner/releases/download/v${runner_version}/actions-runner-linux-x64-${runner_version}.tar.gz" \
    -o "$archive"
  printf '%s  %s\n' "$runner_sha256" "$archive" | sha256sum --check --status
  tar -xzf "$archive" -C "$runner_dir"
  chown -R "$runner_user:$runner_user" "$runner_dir"
fi

if [ ! -f "$runner_dir/.runner" ]; then
  runuser -u "$runner_user" -- "$runner_dir/config.sh" \
    --url "$runner_url" --token "$registration_token" \
    --name "$runner_name" --labels "$runner_name" \
    --work _work --unattended --no-default-labels
fi
unset registration_token

install -d -m 755 /usr/local/libexec
cat > "$cleanup_hook" <<HOOK
#!/usr/bin/env bash
set -euo pipefail
workspace='${runner_dir}/_work/${repo}'
if [ -d "\$workspace" ]; then
  find "\$workspace" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
fi
rm -f -- '${runner_home}/.ssh/id_ed25519' '${runner_home}/.ssh/known_hosts'
if [ '${repo}' = mylifemanager ]; then
  rm -rf -- /tmp/mylifemanager-smoke-screenshots
fi
HOOK
chmod 755 "$cleanup_hook"

cat > "/etc/systemd/system/${service}" <<UNIT
[Unit]
Description=GitHub Actions runner for ${repo}
After=network-online.target
Wants=network-online.target
OnFailure=server-monitoring-failure@%n.service
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=${runner_user}
Group=${runner_user}
WorkingDirectory=${runner_dir}
Environment=HOME=${runner_home}
Environment=ACTIONS_RUNNER_HOOK_JOB_COMPLETED=${cleanup_hook}
ExecStartPre=${cleanup_hook}
ExecStart=${runner_dir}/run.sh
Restart=always
RestartSec=15
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=${runner_dir} ${runner_home}
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
CPUQuota=175%
MemoryMax=${memory_limit}
TasksMax=1024

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$service"
systemctl restart "$service"
systemctl is-active --quiet "$service"
echo "${service}: active"
