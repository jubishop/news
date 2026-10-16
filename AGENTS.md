# News project instructions

<!-- project-starter:begin -->
Project Starter manages this block; add project rules after it. Project rules
take precedence over this block and the foundation pages wherever they differ.

- Keep durable guidance and non-derivable context in [memory](memory/README.md),
  and designs, decisions, and research in [docs](docs/README.md). Before
  non-trivial work or writing memory, search with `bin/knowledge search "term"`
  or `bin/knowledge query "question" --no-rerank`, then read results with
  `bin/knowledge get <path> -l 80`. Markdown sources are authoritative.
- If configured QMD fails, tell the user immediately and attempt repair. If
  repair fails, pause knowledge-dependent work until the user approves a
  fallback; never silently substitute `rg` or direct reads. See
  [search failures](docs/foundation/knowledge-search.md#search-failures).
- Use td for work with multiple stages, interruptions, blockers, or handoffs;
  run `td usage --new-session -q` once per new context and keep handoffs
  current. See [task tracking](docs/foundation/task-tracking.md).
- Follow the [engineering policy](docs/foundation/engineering-policy.md):
  fewer dependencies, red-green tests for behavior changes, cohesive files and
  pages, checkout-isolated validation, and the latest stable toolchains.
- Commit [changes outside the runtime](docs/foundation/engineering-policy.md#changes-outside-the-runtime),
  such as Markdown, AI skills, tests, CI, and tooling, directly on the default
  branch and push them without checks or a pull request.
- For code the application runs, run
  [checks](docs/foundation/engineering-policy.md#checks) by change: the
  relevant application checks while editing, and `bin/check --full` before
  merge or release unless an enforced CI gate runs it. Reuse passing results.
- Keep accepted decisions separate from proposals, preserve unrelated changes,
  and keep secrets and generated caches out of Git.
- Run `bin/setup` after cloning, `bin/doctor` to diagnose setup, and
  `bin/qmd-index` after uncommitted knowledge edits. Managed files listed in
  `.project-starter.json` change only through Project Starter or a recorded
  override with its reason.
<!-- project-starter:end -->

## Project

Read the [concept](docs/concept.md) for the project's direction and the
[implementation design](docs/implementation-design.md) for the selected
Python, Flask, and SQLite stack. Read the [server contract](docs/server-contract.md)
and [operations guide](docs/server-operations.md) for server v1. Read
[worker operations](docs/worker-operations.md) for the Claude Code worker and
its required after-merge commissioning.

Use [GitHub Issues](https://github.com/jubishop/news/issues) for shared work
and acceptance criteria.

`bin/check --full` runs `bin/check-application`: the package import check,
application tests, the browser test, and ShellCheck for the operations and
worker scripts. Run relevant application checks explicitly for code edits.
CI does not enforce branch protection, so run `bin/check --full` locally
before delivery.

Before pushing or merging to `main`, assess the complete delivery under the
[deployment policy](docs/deployment.md#deployment-decisions). Record a skip
decision only for functionally immaterial changes with no outstanding material
release. Full CI checks still run.
