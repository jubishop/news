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
Python 3.14, the minimum, and on the latest stable Python for every
push and PR. Both must pass before deployment. A push to `main`, including
a merged PR, deploys after validation succeeds unless it carries the
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
2. [receive-release](../ops/receive-release), the restricted SSH key's forced
   command, accepts only `status` and `deploy COMMIT_SHA`. It rejects archive
   traversal, links, special files, and archives over 25 MiB. It also refuses
   the release, before changing anything, when the archive's
   [deploy kit](#deploy-kit) files differ from the installed kit. Each attempt
   gets a separate release directory under `/opt/news/releases` that holds
   only `news/`, `requirements.txt`, and a `REVISION` file.
3. The kit's [install-server](../ops/install-server) takes a host lock shared
   by manual and automated installs. Before downtime, the kit's
   [build-environment](../ops/build-environment) installs the locked
   dependencies as `news`. The installer then stops all News writers, takes a
   consistent local SQLite checkpoint as `news`, switches the release link,
   installs the kit's systemd units, and runs `news.cli init-db` as `news`.
4. The installer starts the web service, checks loopback health, runs
   `news-maintain.service` once, and enables the maintenance and backup timers.
   GitHub then checks public HTTPS health before reporting deployment success.

Systemd owns the release process, with a 15-minute limit. An SSH disconnect
does not kill the installer. Its output is in `journalctl -u news-deploy-*`
and is copied into the GitHub Actions log when the SSH session completes.

### Deploy kit

The deploy key's `authorized_keys` entry runs as root, so root runs only a
deploy kit that the owner installs from Git, never anything that arrives over
the key. The kit is [receive-release](../ops/receive-release), installed at
`/usr/local/sbin/news-receive-release`, and these files in
`/usr/local/lib/news-deploy`, all root-owned:

- [install-server](../ops/install-server), which installs a release.
- [build-environment](../ops/build-environment), which builds a release's
  Python environment.
- [rebuild-environment](../ops/rebuild-environment), linked from
  `/usr/local/sbin/news-rebuild-environment` for
  [Python runtime updates](server-operations.md#production-python).
- Every [systemd unit](../ops/systemd), which the installer copies to
  `/etc/systemd/system`.

The receiver defines this list. It caps its own address space before parsing,
so a hostile archive cannot exhaust the small, swapless shared host while it
reads the upload. It extracts only `news/` and `requirements.txt` into a
release, root-owned and read-only to `news`. Installing the requirements can
run package build code, so build-environment runs `venv` and `pip` as `news`
in a transient unit that can write only the new environment. Systemd stops any
process the build leaves behind. Root then takes ownership of the environment
and re-checks it, rejecting anything not root-owned or with unsafe modes, in
case a lingering `news` process added a file during the handover. The migration
and the import check run as `news` under the same sandbox as the services. Root
never runs the release's environment; migrations, maintenance, and the services
run as `news`, and the database checkpoint uses the shared runtime as `news`.
The key can still deploy any release whose kit files match, and that release's
code runs as `news` with the application's data and credentials.

A deployment compares the archive's kit files, which `git archive` takes from
the tested commit, with the installed kit by digest. When a commit changes a
kit file, its deployment fails with a message naming
`bin/install-deploy-kit`. From a trusted checkout, with the owner's SSH
access rather than the deploy key, run:

```sh
bin/install-deploy-kit root@YOUR_SSH_HOST REVISION
```

It sends the kit files from `git archive REVISION ops/`, never the working
tree, and computes the digest by running that revision's own `receive-release`
locally to select the kit, so the installer, the host receiver, and the deploy
job agree on the files and digest. Under the deployment lock, the host replaces
the kit, removes kit files that the revision no longer has, and reports the
digest, which must match. Then rerun the failed deploy job with **Run
workflow** on `main`. Installing a kit changes no running service; the next
deployment installs its units. A later deployment of a revision with a
different kit fails until its kit is installed. `status` prints the active
revision and the installed kit digest.

Each release builds its Python environment once as `news`, and
[build-environment](../ops/build-environment) refuses a `.venv` that already
exists. The receiver gives every deployment a fresh release directory, so this
never affects automated releases. A manual `install-server` rerun against a
release directory whose build already started must use a new directory (or a
new deployment); do not rerun it over a partially built one.

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

On the VPS, create `/opt/news/releases` and install the [deploy kit](#deploy-kit)
with `bin/install-deploy-kit`. Install `restic`, `curl`, and `util-linux`
(for `flock` and `runuser`), and confirm the shared
[Python runtime](server-operations.md#production-python). Add a
dedicated public deployment key to root's `authorized_keys` with:

```text
restrict,command="/usr/local/sbin/news-receive-release" ssh-ed25519 PUBLIC_KEY news-github-deploy
```

This key cannot open an interactive shell, transfer arbitrary files, or create
SSH forwarding tunnels, and root runs only the installed kit for it. It can
still deploy releases whose code runs as `news`; protect `main` and the
production environment accordingly. Installing or updating the kit is an
explicit host administration step with the owner's access, outside releases.

The VPS answers SSH only on its tailnet address, so the deploy job first joins
the tailnet as an ephemeral `tag:ci` node with `tailscale/github-action` and
pings the VPS. It authenticates through a Tailscale federated identity limited
to the subject `repo:jubishop/news:environment:production`, which needs the
job's `id-token: write` permission; no Tailscale secret is stored in GitHub.
The tailnet policy and setup live in vps-infra `docs/tailscale.md`.

Create the GitHub environment `production`, with a custom branch rule for
`main`, and configure:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `NEWS_DEPLOY_SSH_KEY` | Dedicated deployment private key. |
| Secret | `NEWS_DEPLOY_KNOWN_HOSTS` | VPS SSH host key for its tailnet address, obtained through an already trusted connection. |
| Secret | `TS_OAUTH_CLIENT_ID` | The federated identity's client ID. |
| Secret | `TS_AUDIENCE` | The federated identity's audience. |
| Variable | `NEWS_DEPLOY_HOST` | The shared VPS's tailnet address. |

Do not use an unchecked `ssh-keyscan` result or disable host verification.
Application, Resend, and R2 credentials remain in `/etc/news` on the VPS.
The workflow deletes its temporary SSH credential files when its job finishes.
The [production hosting reference](../memory/production-hosting.md) records
the installed host, Cloudflare scope, and private recovery-copy locations.

## Migrations and other release work

`news.cli init-db` is the migration entry point and runs on every release.
It uses SQLite's `user_version` to apply schema work once and rejects a newer
database rather than downgrading it. Current schema version 3 applies the
initial schema and then each [numbered migration](../news/migrations) in order;
rerunning it preserves existing data.

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
check establish that it is running. Failed release directories remain for
inspection until the next successful deployment, which removes every release
except itself and the release it replaced. Deployments run one at a time; do
not upload a manual release while one is running.

If only public HTTPS verification failed, the origin may already be healthy.
Check DNS, TLS, and the proxy before retrying. Use **Run workflow** on `main`
or push a fix. Rerunning a superseded commit skips deployment. A deployment
still running after a client disconnect holds the host lock; wait for its
systemd result before retrying.

Installer tests use disposable Linux roots with external commands replaced
at their boundaries. They exercise the real shell script, including failure
paths, without accessing host service or database paths. These tests run in
Linux CI; macOS skips them. The release client, archive receiver, environment
build, and kit installer tests run on both platforms.
