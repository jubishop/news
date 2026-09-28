---
status: current
---

# Server setup and operations

This is the runbook for server v1. See [worker operations](worker-operations.md)
for the local Codex worker and after-merge commissioning. The server is reviewable locally without an
AI worker. After one-time provisioning, the [deployment workflow](deployment.md)
releases validated pushes to `main`, including migrations and maintenance.

## Runtime and local setup

Application support: Python 3.12–3.14, tested on Ubuntu 24.04 in CI and macOS
for development. The production target uses Ubuntu's Python 3.12. Foundation
commands retain their separate Python 3.9+ policy. Shell scripts use POSIX sh.
Restic 0.16–0.19 is supported for backup operations (Ubuntu 24.04 packages 0.16).
ShellCheck and Restic must be on PATH for full validation.

```sh
bin/setup
bin/app-setup
bin/check-app
bin/preview
```

`bin/app-setup` uses `python3.12` by default; set `NEWS_PYTHON` to another
supported executable if needed. It creates a checkout-local `.venv`, installs
the hash-locked production and test requirements, and installs Chromium.
On Linux, install Chromium system packages with
`.venv/bin/python -m playwright install --with-deps chromium`.

The alternative for development is `uv sync --locked` followed by
`uv run playwright install chromium`. `uv.lock` pins the same dependencies.
When changing dependencies, refresh both hash exports with `uv export --frozen
--no-dev --no-emit-project --format requirements-txt --output-file requirements.txt`
and `uv export --frozen --only-dev --format requirements-txt --output-file
requirements-dev.txt`. Production installs only `requirements.txt`.

Flask supplies routing, forms, sessions, and templates. Gunicorn provides a
bounded production HTTP process. Markdown-it-py supplies a maintained
CommonMark parser. PyJWT and cryptography verify Access signatures. These avoid
implementing parsers or cryptography in the application. Playwright is a test
only dependency for real browser behavior. Scheduling, persistence, search,
HTTP email delivery, and backup measurement use standard libraries.

The preview binds `127.0.0.1:3071` with disposable SQLite data and clearly
labeled sample articles. It prints the path to fixture owner headers for a
browser automation tool. It exercises real owner/worker endpoints with a
locally generated signing key and a fake external JWKS response. There is no
production authentication bypass. Stop it with Ctrl-C; its database is removed.
Do not bind this fixture to a public interface.

`bin/check-app` runs API/lifecycle tests, a real local Restic backup and restore,
a browser journey, and deployment shell lint. Tests fake Cloudflare, R2, and
Resend at their network boundaries. Browser tests cover reporter controls,
Trash/restore, public reading, and mobile layout. Screenshots go under ignored
`test-results/` in this checkout. No test uses real service credentials or sends
email. Test runs are sequential; the concurrency case alone deliberately races
two requests against one temporary SQLite database.

`bin/check --full` first runs all foundation checks, then `bin/check-app`.
The default and `--documents-only` modes do not run application tools. CI runs
full validation on Python 3.12, 3.13, and 3.14. Source discovery and output stay
inside the active checkout; `.venv`, `var`, and nested worktrees are excluded.

## Provisioning prerequisites

Use the shared procedures in `~/projects/vps-infra`. Preserve other hosted
applications and existing firewall rules. The September 25, 2026 inventory
found port 3070 free; confirm this before rollout.

1. Create a proxied `news.jubishop.com` DNS record to the shared VPS. Use
   Cloudflare Full (strict) TLS and a valid origin certificate in
   `/etc/caddy/certs/news.pem` and `news.key`, readable by Caddy.
2. Create an Access application covering both `/newsroom` and `/newsroom/*`.
   Allow only the selected owner email. Create a separate application covering
   `/api` and `/api/*` with a **Service Auth** policy for a dedicated News worker
   service token. Do not protect the public reading routes with Access.
   Record distinct application AUD values. Test the exact bare paths as well
   as descendants; avoid a policy that covers only a trailing-slash URL.
   During the server-only phase, the API application can deny everyone until
   its dedicated worker service token is available. Keep the separate audience
   configured; do not substitute an owner token or an authentication bypass.
3. Create a dedicated private R2 Standard bucket, scoped object credentials,
   and a Restic encryption password. Keep a recoverable copy of that password
   outside the VPS. Initialize the repository once with `restic init` using
   those credentials. Never initialize a replacement over a recovery repository.
4. Configure the approved Resend sending key for the verified sending domain.
   The owner authorized reuse of the existing sending-only key on September 25,
   2026; see the [email decision](implementation-design.md#email-delivery).
   Set the sender to `News <news@jubishop.com>` and put the privately selected
   owner recipient in configuration. Coordinate rotation with other consumers
   of the shared key.
5. Install `python3.12-venv`, `restic`, and `curl` on the server. Create root-owned
   `/etc/news/app.env` and `/etc/news/backup.env`, mode 0600. Copy the shapes from
   [.env.example](../.env.example) and [backup example](../ops/backup.env.example).
   Use `/var/lib/news/news.sqlite3` for `NEWS_DATABASE` and
   `/var/lib/news-backup/size.json` for `NEWS_BACKUP_STATE`. Generate a private
   random `NEWS_SECRET_KEY` of at least 32 characters. Fill all Access, email,
   and backup credentials. Keep these files outside release directories.

The application verifies JWTs independently of Cloudflare's edge policy.
Bind Gunicorn only on loopback. Keep the shared host's 80/443 firewall limited
to Cloudflare; do not expose 3070. A service credential must fail on newsroom
routes, and an owner credential must fail on worker routes.

Reference: Cloudflare's [JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/),
[service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/),
and [application token claims](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/)
were checked September 25, 2026. Verify provider configuration again at rollout.

## Release and first rollout

Only deploy a reviewed revision with successful full validation. Export that
revision (for example with `git archive`) into `/opt/news/releases/REVISION` on
the VPS. Do not copy `.venv`, caches, local `.env` files, or preview databases.
Run the uploaded `ops/install-server /opt/news/releases/REVISION` as root.
The [automatic workflow](deployment.md) performs this sequence for pushes to
`main`; use manual installation only for operator-led recovery or setup.

The installer builds the production environment before stopping any service.
It uses a dedicated unprivileged `news` account and root-owned release code.
It stops all News writers, makes a consistent local pre-release SQLite backup
when a database exists, switches the release link, applies migrations, starts
the web service, checks loopback health, and runs maintenance once. It then
enables the regular timers. A failure after shutdown starts leaves services
stopped for explicit recovery. It does not automatically downgrade the database
or change the Caddy configuration. A host lock prevents overlapping installs.

After origin health passes, add the [Caddy fragment](../ops/Caddyfile.fragment)
without replacing unrelated sites. Validate Caddy, then reload it. Verify:

- Public HTTPS feed and full article rendering.
- Anonymous newsroom/API requests denied, including direct origin requests
  without a JWT. A forged JWT and the wrong audience must fail.
- Owner login, reporter creation/edit/pause/resume, history, Trash, and restore.
- Worker service-token discovery, claim, result, identical result retry, and
  cross-role rejection using disposable acceptance data before real reporting.
- `news-maintain.timer`, `news-backup.timer`, and `news-restore-check.timer` active.
- One successful `systemctl start news-backup.service`, then
  `systemctl start news-restore-check.service`; inspect status and the newsroom.
- A real delivery test to the configured owner, with its provider receipt, before
  treating email monitoring as commissioned. Automated tests do not establish
  real account permissions or inbox delivery.

The web service uses one Gunicorn process and two threads, a 256 MB ceiling,
and 75% CPU quota. Maintenance and backup jobs have separate bounds. Measure
actual usage alongside other VPS applications and adjust if needed. Keep the
AI worker off this server. Production starts with an empty database; fixture
stories and reporters are never installed by the release script.

## Monitoring and email

`maintain` runs every five minutes. It materializes scheduled dates, identifies
missing signals, purges expired Trash, and delivers queued notices. Neither
page views nor the external worker drive this timer.

Leave `NEWS_MONITOR_WORKER=false` during the server-only phase. Once the real
worker is ready, set it true and set `NEWS_MONITOR_START_DATE` to its first
expected Pacific check-in day. Restart the service; subsequent maintenance
processes also read the new environment. Report due dates remain visible even
before worker commissioning. Worker monitoring is about daily contact, not AI
coverage or a scheduled execution hour.

After a complete day without a check-in, one worker-outage incident opens.
Repeated missing days update it without another email. Per-run overdue or
failure emails are suppressed while that outage is active; their details stay
visible. A current check-in resolves the outage. A later outage can create a
new email. With healthy daily contact, an overdue or exhausted run gets its own
notice. Completion, superseding, removal, or reopening resolves the relevant
notices. A later successful recurring result resolves older failure notices
for that reporter while leaving the failed runs in history.

Email payloads and keys are saved before sending. Resend requests happen outside
database transactions, use a stable idempotency key, and retry on the next
maintenance pass (at least five minutes apart). A successful provider receipt
is persisted. This means accepted by Resend, not proof of inbox delivery.
After 23 hours of uncertain delivery, automated retries stop to avoid sending
a duplicate beyond the provider's idempotency window. The newsroom displays a
reconciliation notice. Check the stored incident ID and provider delivery log;
record a confirmed receipt or resolve the incident with a documented operator
DB update. Do not simply clear the first-attempt timestamp when delivery is
unknown. Missing credentials disable delivery, so check configuration at rollout.

## Backups and recovery

The [backup policy](backups.md) retains seven daily and four weekly snapshots.
The daily timer runs around 4:20 AM Pacific, with up to ten minutes of jitter.
The weekly restore check runs Sunday around 5:30 AM Pacific. The shared backup
lock prevents concurrent repository work.

`backup` uses SQLite's backup API to write a mode-0600 snapshot, encrypts it with
Restic, and only then runs retention cleanup. It measures all bucket listing
pages after successful cleanup, saves the last successful size atomically, and
opens one warning above 1,000,000,000 bytes. Strictly below rearms the warning;
equality does neither. Failed measurements retain the prior size and incident.
Temporary plaintext snapshots are removed even on handled failure.

`restore-check` reads and validates all Restic data, restores the latest News
snapshot into a private temporary directory, then checks SQLite integrity,
foreign keys, schema version, and all six application table queries. It accepts
schema 1 or 2; schema 2 also checks the archive metadata table and revision column. It removes this test
restore without touching the running database. Successful state is saved in
`/var/lib/news-backup/restore.json`. A backup or restore failure opens an email
incident; abrupt host/process failures still require checking systemd status.

Inspect `journalctl -u news -u news-maintain -u news-backup -u news-restore-check`.
Provider bodies and credentials are not logged. The newsroom shows unresolved
incidents and the latest successful storage measurement. Disk/RAM exhaustion
can prevent even local incident writes; host monitoring remains necessary.

For actual recovery, stop all News services and timers first. Restore the chosen
snapshot into a separate private directory with Restic, run the same integrity
and version checks, and retain the failed database separately. Replace the live
SQLite database only after verification, remove its obsolete `-wal`/`-shm`
sidecars while all writers remain stopped, and restore ownership/mode 0600.
Start a release compatible with that schema, verify health/auth/content, then
restart timers. Do not restore a database while Gunicorn is running.

For a failed release, `/var/lib/news-backup/pre-release.sqlite3` is the local
consistent checkpoint. Restore it only as part of an explicit rollback after
checking whether the new release accepted any writes; an older checkpoint can
lose newer data. Restore the prior release link as well. One local checkpoint
is overwritten by the next release; encrypted R2 history provides off-host
recovery. Deleting an article removes live content after 30 days, but content
inside old backups remains until retention removes those snapshots.
