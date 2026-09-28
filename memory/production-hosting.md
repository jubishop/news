---
name: production-hosting
description: Installed News infrastructure, credential locations, and recovery constraints.
type: reference
---

# Production hosting

News uses the shared `bishop` VPS at `5.78.193.133`, with the public hostname
`news.jubishop.com`. These provisioning facts were verified September 25, 2026.
Use the [deployment guide](../docs/deployment.md) for release behavior and the
[operations guide](../docs/server-operations.md) for backup and recovery commands.
Track rollout progress and remaining acceptance work in GitHub Issues.

## Host and Cloudflare boundaries

- News runs as the `news` system user on loopback port 3070. Caddy forwards
  the News hostname to that port. Preserve the other applications on this host.
- On September 28, 2026, CPython 3.14.7 was installed for News under
  `/opt/news/python`, with `/opt/news/python3.14` pointing to its interpreter.
  The tree is root-owned and executable by `news`. The provisioning tool is
  uv 0.12.18 in `/opt/news/tools`; it does not modify shell profiles.
  Ubuntu's `/usr/bin/python3` remains 3.12.3. Follow the
  [runtime procedure](../docs/server-operations.md#production-python) for upgrades.
- The DNS A record is proxied through Cloudflare. The origin certificate and
  private key are `/etc/caddy/certs/news.pem` and `news.key`, owned by
  `root:caddy`, mode 0640. The certificate covers only `news.jubishop.com`.
- Cloudflare's **News strict origin TLS** configuration rule applies strict
  certificate validation only to that hostname. The shared zone uses Full TLS
  for other applications. Do not change the whole zone to strict without
  checking their origin certificates.
- Separate Access applications cover `/newsroom` plus `/newsroom/*`, and
  `/api` plus `/api/*`. The newsroom allows only the selected owner. The API
  denies everyone during the server-only phase. Its worker service token is a
  separate commissioning step. Keep worker monitoring disabled until then.
- The Access issuer is `https://jubishop.cloudflareaccess.com`. App identifiers
  and distinct audiences are recorded privately in `~/.config/news/cloudflare.json`.
- On September 26, 2026, the owner application and shared Access organization
  login session were set to `730h` (one month) and verified through the API.
  The owner policy inherits the application duration. The worker application
  retains its separate `12h` duration and deny policy.
- The owner application uses only the shared Google identity provider, with
  automatic redirect to Google. Browser sign-in was verified on September 26,
  2026. The shared provider and its private credential recovery location are
  documented in `~/projects/vps-infra/memory/cloudflare.md`.

## Private configuration and recovery copies

The VPS has root-owned mode-0600 `/etc/news/app.env` and `/etc/news/backup.env`.
They stay outside the immutable release directories. The database is
`/var/lib/news/news.sqlite3`; backup state is in `/var/lib/news-backup`.

The owner's Mac keeps mode-0600 recovery files under the mode-0700 directory
`~/.config/news/`:

| File | Purpose |
| --- | --- |
| `app.env` | Private application settings and the approved Resend key. |
| `backup.env` | R2 endpoint, bucket-scoped S3 credentials, and Restic password. |
| `restic-password` | Standalone copy of the stable backup encryption password. |
| `app-secret` | Stable application session secret. |
| `deploy_ed25519` | Dedicated restricted deployment SSH key. |
| `known_hosts` | Pinned VPS SSH host key. |
| `news.key` and `news.pem` | Origin TLS recovery files. |

Keep these paths private and out of Git. Update the relevant copies together
when rotating credentials. Losing both copies of the Restic password makes
the encrypted backups unusable. Temporary transfer files such as
`~/.news-backup.env` are not recovery locations; remove them after a verified
transfer.

The R2 Standard bucket is **news-backups**, with public access disabled. The
**News VPS backups** account token permits object read/write only in that
bucket, with no expiry. Store its S3 credentials on the VPS; the broad
Cloudflare administration token is not required there. The encrypted Restic
repository is initialized. Inspect existing snapshots before any recovery
operation; do not run `restic init` as a routine deployment step.

The owner approved reuse of the existing Resend sending-only key from `~/.env`.
See the authoritative [email decision](../docs/implementation-design.md#email-delivery).
The selected owner login and alert address remain in private configuration.
The sender is `News <news@jubishop.com>`.

## Deployment identity

GitHub's `production` environment permits `main`. It contains the dedicated
SSH key and pinned host-key secrets and the VPS host variable. The root SSH
authorized-key entry forces `/usr/local/sbin/news-receive-release` with SSH
restrictions. It cannot open a shell or create forwarding tunnels. It can
install trusted releases as root, so protect changes to `main`.

The receiver is installed separately from application releases. The selected
release is `/opt/news/current`; its `REVISION` file records the deployed commit.
The receiver uses the dedicated News Python interpreter. The prior Python 3.12
receiver is retained at `/opt/news/receiver-backups/receive-release-before-python314`,
owned by root with mode 0600, for operator-led recovery.
Keep provider credentials out of GitHub deployment logs and release archives.
