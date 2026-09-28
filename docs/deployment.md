---
status: current
---

# Automatic production deployment

The owner requested automatic deployment from `main` on September 25, 2026,
including database migrations and release maintenance. The reason was that
server v1 had merged successfully but had not reached `news.jubishop.com`.
This supersedes the earlier PR-only delivery scope for server implementation.

## Release workflow

[Repository checks](../.github/workflows/check.yml) runs full validation on
Python 3.12, 3.13, and 3.14 for every push and PR. A push to `main`, including
a merged PR, deploys after all three jobs succeed unless it carries the
explicit skip decision described below. PR checks cannot deploy or read
production credentials. A manual run on `main` requests deployment even when
the commit carries a skip decision; it performs the same checks first.

The production environment permits only the `main` branch. A new push does
not cancel a running deployment. Runs are serialized, and a waiting run can
be replaced by a newer push. Before upload, the deploy command checks that
the tested revision is still the tip of `main`; it skips superseded revisions.
Thus rapid pushes can deploy only the newest tested revision, rather than
every intermediate commit. Database migrations must support that normal case.

The workflow uses these entry points:

1. [deploy-main](../ops/deploy-main) exports the tested commit with `git archive`.
   Only `news`, `ops`, and the production requirements are uploaded. Local
   environment files, databases, Git credentials, and test fixtures are absent.
2. [receive-release](../ops/receive-release) accepts only `deploy COMMIT_SHA`
   through a restricted SSH key. It rejects archive traversal, links, special
   files, and archives over 25 MiB. Each attempt gets a separate release
   directory under `/opt/news/releases`, with a `REVISION` file.
3. [install-server](../ops/install-server) takes a host lock shared by manual
   and automated installs. It installs locked dependencies before downtime,
   stops all News writers, takes a consistent local SQLite checkpoint, switches
   the release link, installs systemd units, and runs `news.cli init-db`.
4. The installer starts the web service, checks loopback health, runs
   `news-maintain.service` once, and enables the maintenance and backup timers.
   GitHub then checks public HTTPS health before reporting deployment success.

Systemd owns the release process, with a 15-minute limit. An SSH disconnect
does not kill the installer. Its output is in `journalctl -u news-deploy-*`
and is copied into the GitHub Actions log when the SSH session completes.

The workflow uses GitHub's
[job dependencies](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
and [concurrency controls](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
checked September 25, 2026. The VPS lock also protects against manual installs.

## Deployment decisions

On September 28, 2026, the owner requested that functionally immaterial changes
stop causing production deployments. The agent preparing the push or merge
assesses the complete delivery and records its decision in the final commit.
CI executes that decision; it does not infer functional impact from filenames.

Deploy changes that can affect the server's behavior, rendered content,
dependencies, data, runtime settings, or production operations. Documentation,
comments, formatting-only edits, and tooling changes that leave the production
release unaffected can skip deployment. Consider the actual effect: Markdown
used as application content can be material, while a source comment can be
immaterial.

Before choosing to skip, confirm production already contains all outstanding
material changes. Review the complete change since that deployed revision,
including earlier commits in the push or merge. A pending or failed material
release still needs deployment; a later documentation commit must not suppress
it. For mixed changes or uncertainty, retain the default deployment.

For a reviewed immaterial delivery, add these Git trailers at the end of the
final commit message, after a blank line, with a specific reason:

```text
News-Deploy: skip
News-Deploy-Reason: Agent instructions only; production contains all material changes.
```

Preserve the trailers in the final squash or merge commit that reaches `main`.
An unmarked commit, a missing reason, or conflicting decisions keeps deployment
enabled. Do not use a CI-skip marker: all validation still runs.

[deployment-decision](../bin/deployment-decision) reads the tested commit's
trailers and supplies the deploy job's condition. A skipped deployment never
starts that job or loads its production credentials. The decision and reason
remain reviewable in Git and in the decision job's log. This relies on the
agent's assessment; it is not an automatic proof that two versions behave alike.

Use **Run workflow** on `main` when an explicit deployment or retry is needed,
including for a commit that previously skipped deployment.

## One-time setup

Automatic releases require the [server provisioning prerequisites](server-operations.md#provisioning-prerequisites).
DNS, TLS, Cloudflare Access, private settings, and the initialized backup
repository must exist before the first successful release. A merge cannot
create provider credentials that the deployment does not have.

On the VPS, create `/opt/news/releases` and install `ops/receive-release` as
root-owned mode 0755 at `/usr/local/sbin/news-receive-release`. Install
`python3.12-venv`, `restic`, `curl`, and `util-linux` (for `flock`). Add a
dedicated public deployment key to root's `authorized_keys` with:

```text
restrict,command="/usr/local/sbin/news-receive-release" ssh-ed25519 PUBLIC_KEY news-github-deploy
```

This key cannot open an interactive shell, transfer arbitrary files, or create
SSH forwarding tunnels. It can install trusted release code with root privileges;
protect `main` and the production environment accordingly. Updating the SSH
receiver itself is an explicit host administration step, outside normal releases.

Create the GitHub environment `production`, with a custom branch rule for
`main`, and configure:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `NEWS_DEPLOY_SSH_KEY` | Dedicated deployment private key. |
| Secret | `NEWS_DEPLOY_KNOWN_HOSTS` | VPS SSH host key obtained through an already trusted connection. |
| Variable | `NEWS_DEPLOY_HOST` | Shared VPS hostname or IP. |

Do not use an unchecked `ssh-keyscan` result or disable host verification.
Application, Resend, and R2 credentials remain in `/etc/news` on the VPS.
The workflow deletes its temporary SSH credential files when its job finishes.
The [production hosting reference](../memory/production-hosting.md) records
the installed host, Cloudflare scope, and private recovery-copy locations.

## Migrations and other release work

`news.cli init-db` is the migration entry point and runs on every release.
It uses SQLite's `user_version` to apply schema work once and rejects a newer
database rather than downgrading it. Current schema version 1 needs only the
initial migration; rerunning it preserves existing data.

When a later feature changes the schema, add and test its forward migration
in [news/db.py](../news/db.py). Support all older deployed versions, update
the restore validator's supported schema, and test a populated database as
well as a fresh one. Running a migration automatically does not make its SQL
safe: data changes still require review and automated tests.

Add other required release tasks to the installer at the appropriate stage,
with explicit failure handling and tests. Tasks must tolerate a repeated release.
Current post-start maintenance materializes schedules, purges expired Trash,
and processes queued notices. Regular maintenance and backups then continue
through their systemd timers. The separate research worker is not installed
or started by this workflow.

## Failed releases and retries

Dependency or lock failure leaves the running release unchanged. After the
installer begins stopping writers, a failed stop, migration, health check, or
maintenance pass fails the deployment and leaves News stopped for recovery.
No database downgrade or automatic snapshot restore occurs. Such a restore
could discard writes made after startup.

Inspect the failed Actions run and the corresponding `news-deploy-*` journal.
Follow [database recovery](server-operations.md#backups-and-recovery) before
restarting a release after a schema failure. `/opt/news/current/REVISION`
identifies the selected code, but only a successful deployment and health
check establish that it is running. Release directories are retained for
inspection; periodically remove old unused releases after checking the current
link and keeping the prior working release.

If only public HTTPS verification failed, the origin may already be healthy.
Check DNS, TLS, and the proxy before retrying. Use **Run workflow** on `main`
or push a fix. Rerunning a superseded commit skips deployment. A deployment
still running after a client disconnect holds the host lock; wait for its
systemd result before retrying.

Installer tests use disposable Linux roots with external commands replaced
at their boundaries. They exercise the real shell script, including failure
paths, without accessing host service or database paths. These tests run in
Linux CI; macOS skips them. The release client and archive receiver tests run
on both platforms.
