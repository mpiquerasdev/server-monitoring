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
