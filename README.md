# Deployment monitoring

Reusable GitHub composite action. A deployment workflow records its Unix start
time as its first step and invokes this action with `if: always()` as its last
step. The result includes the service, public URL, elapsed time and link to the
workflow run. The bot token and one authorized private chat ID are repository
secrets; neither belongs in source control.

The action reports workflow failures, including build or SSH errors. It cannot
report a GitHub Actions run that never starts or a total Telegram outage.
