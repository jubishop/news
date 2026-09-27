# News

A personal news agency staffed by AI reporters. The owner acts as editor in
chief: hire reporters, assign their beats, and choose how often they report.
Read their articles on a public news site with a newest-first feed and a
reporter filter. The newsroom is owner-only, and the API requires authentication.

The [product design](docs/product-design.md) develops the
[concept](docs/concept.md). The [implementation design](docs/implementation-design.md)
selects Python, Flask, SQLite, and a separate reporting worker. Server v1
implements the public edition, owner newsroom, authenticated worker API,
monitoring, and backup commands. The Mac worker runs vanilla Codex with Luna through the existing subscription.
See [worker operations](docs/worker-operations.md) for setup and the 06:00
Pacific cron installation after merge. See the
[server contract](docs/server-contract.md) and
[operations guide](docs/server-operations.md) for the implemented interface
and deployment prerequisites.

Use [GitHub Issues](https://github.com/jubishop/news/issues) for work items
and implementation progress.

## Development

Run `bin/setup` after cloning. It requires Git and Python 3.9 or later.
QMD and direnv are optional; setup reports skipped features.

The application requires Python 3.12–3.14. Install ShellCheck and Restic, then
run `bin/app-setup` to create the local environment and browser test dependency.
Run `bin/check-app` for application checks and `bin/preview` for a disposable
local edition at `http://127.0.0.1:3071`. The preview uses test data and fixture
Access credentials; it does not contact a production worker. See
[local setup](docs/server-operations.md#runtime-and-local-setup).

Use `bin/check --documents-only` for Markdown edits and `bin/check` for
foundation checks only. Use focused local checks for ordinary code changes.
Run `bin/check --full` locally after setup, test/build infrastructure changes,
or when focused checks leave material uncertainty. Require successful full
validation before merge or release; an enforced full CI gate can provide it
for ordinary changes. Without that gate, run the full check locally before
delivery. See the [validation policy](docs/development-workflow.md#checks-and-project-extensions).
The fast and full checks require ShellCheck.
Use `bin/doctor` for diagnostics. See the
[development workflow](docs/development-workflow.md) for search, worktrees,
hook integration, and recovery.

## Knowledge

- [Memory](memory/README.md): durable guidance and non-code context.
- [Docs](docs/README.md): designs, decisions, research, and reference guides.

The [GitHub Actions workflow](.github/workflows/check.yml) runs the full
foundation and application checks for pull requests and pushes to `main`.

The foundation comes from
[Project Starter](https://github.com/jubishop/project-starter), with its exact
source revision in [.project-starter.json](.project-starter.json) and its
license notice in [LICENSE.project-starter](LICENSE.project-starter).

## License

[MIT](LICENSE), selected by the owner on September 24, 2026. The separate
starter notice is retained with the copied foundation.
