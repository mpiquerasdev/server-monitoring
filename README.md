# Server monitoring

Reusable GitHub composite action. A deployment workflow records its Unix start
time as its first step and invokes this action with `if: always()` as its last
step. The result includes the service, public URL, elapsed time and link to the
workflow run. The bot token and one authorized private chat ID are repository
secrets; neither belongs in source control.

The action reports workflow failures, including build or SSH errors. It cannot
report a GitHub Actions run that never starts or a total Telegram outage.

`healthcheck.py` runs hourly as a systemd timer on the production server. It
checks the public HTTPS endpoint of each application twice before declaring a
failure, saves the last state in `/var/lib/server-monitoring/status.json`, and
sends one critical alert per failure and one recovery alert. It does not send
hourly success noise. Configuration lives in `/etc/server-monitoring.env`
(mode 0600) and contains only the bot token and authorized private chat ID.
The same timer checks installed `gh-runner-*.service` units and alerts on
failure and recovery. A unit that exhausts its restart limit also invokes the
monitoring failure notifier immediately.

`install-actions-runner.sh` installs one repository-scoped runner on
`vps-5sitios`. Each runner has its own system user, workspace and label
`vps-5sitios-<repository>`, without `sudo` or Docker group membership.
Systemd limits it to 3 GiB (3.5 GB for MyLifeManager and 5Sitios) and 175% CPU. The completed-job hook removes the
checked-out source and temporary SSH key. Heavy builds share
`/run/lock/gh-ci-build.lock`, created by systemd-tmpfiles at boot. Keep that
lock around any new Next or Docker build stage.

The registration token is short-lived and must be piped to the installer on
stdin. Never save it in a workflow, shell history, or log. To inspect a runner,
use `systemctl status gh-runner-<repository>.service` on the VPS and the
repository's GitHub Actions runner settings. The `server-monitoring` public
repository intentionally remains on GitHub's hosted runner.

The MyLifeManager Playwright smoke test needs Chromium's system fonts. Install
`fontconfig-config` and `fonts-liberation` on the VPS and check that
`/etc/fonts/fonts.conf` exists. Its Verify job checks this before launching the
browser; `npx playwright install chromium` alone does not install the OS fonts.

Reviok's backend Verify suite uses the separate `reviok-ci-mongo` container on
`127.0.0.1:27017`, with a tmpfs data directory. It must never use the production
MongoDB. Check it with
`docker exec reviok-ci-mongo mongosh --quiet --eval 'db.adminCommand({ping:1}).ok'`.

`docker-cleanup.sh` runs daily and removes only stopped containers, unused
images and networks older than 72 hours. It caps unused BuildKit cache at
6 GiB. It never prunes Docker volumes or the 5Sitios bind mount containing
SQLite, Redis and videos. The older 5Sitios-only BuildKit timer is replaced by
this shared maintenance timer; the separate 5Sitios frontend image cache timer
remains enabled.
