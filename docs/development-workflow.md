---
status: current
---

# Development workflow

This page records this project's own commands and integrations. Shared rules
are in the [foundation pages](foundation/README.md).

News uses Python, Flask, and SQLite. See [server operations](server-operations.md)
for application setup and [automatic deployment](deployment.md) for releases.
Use [GitHub Issues](https://github.com/jubishop/news/issues) for actionable work.

## Setup

```sh
bin/setup
bin/doctor
bin/check --full
```

Setup needs Git and Python 3.9 or later, and checks also need ShellCheck.
QMD and direnv are optional; setup reports skipped features. Install td and
run `td init` as described in [task tracking](foundation/task-tracking.md).
Create `.envrc` only when the project needs environment settings, and review
it before running `direnv allow`; search does not need it.

Run `bin/app-setup` before application checks, as described in
[local setup](server-operations.md#runtime-and-local-setup).

## Checks

Follow the [check schedule](foundation/engineering-policy.md#checks).
`bin/check-application` imports the `news` package, runs the application tests
in `tests/app`, runs the browser test, and lints the deployment and worker
shell scripts with ShellCheck, using the checkout-local `.venv`. Application
setup, supported Python versions, and test requirements are in the
[operations guide](server-operations.md).

The [GitHub Actions workflow](../.github/workflows/check.yml) runs
`bin/check --full` on Ubuntu 24.04 for pull requests and pushes to `main`.
It installs ShellCheck, Restic, locked Python dependencies, and Chromium; it
checks Python 3.14, uses read-only repository permissions, and does not
persist checkout credentials. This initial setup does not enforce branch
protection, so full local validation is required before delivery. Verify the
workflow result for the exact pushed commit.

## Runtime and toolchain versions

The application, CI, the worker, and production use Python 3.14, declared in
`pyproject.toml` and checked by `bin/app-setup` and `ops/install-server`.
Foundation commands keep their Python 3.9 or later requirement. Restic
0.16–0.19 is supported for backups. See the
[runtime decision](server-operations.md#runtime-and-local-setup) and the
[version policy](foundation/engineering-policy.md#runtime-and-toolchain-versions).

## Deployment

A push to `main` deploys after full validation unless its final commit records
a reviewed skip decision with `News-Deploy` trailers. Use **Run workflow** on
`main` to deploy explicitly. See [automatic deployment](deployment.md) and its
[deployment decisions](deployment.md#deployment-decisions), following the
[deployment policy](foundation/engineering-policy.md#deployment-decisions).

## Project Starter

`.project-starter.json` records the installed Project Starter release and the
hashes of its managed files. Update them with Project Starter's `bin/sync`,
and record any intentional local change as an override with its reason.
