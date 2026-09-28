# News project instructions

Read the [concept](docs/concept.md) for the project's direction and the
[implementation design](docs/implementation-design.md) for the selected
Python, Flask, and SQLite stack. Read the [server contract](docs/server-contract.md)
and [operations guide](docs/server-operations.md) for server v1. Read [worker operations](docs/worker-operations.md) for the vanilla Codex worker
and its required after-merge commissioning.

Keep designs, decisions, and research in [docs](docs/README.md). Use the
[GitHub Issues](https://github.com/jubishop/news/issues) for work items and
implementation progress.

Before non-trivial work or writing memory, search the relevant knowledge.
Use `bin/knowledge search "term"` for known terms and
`bin/knowledge query "question" --no-rerank` for broader questions.
Read focused results with `bin/knowledge get <path> -l 80`.
Use direct reads or `rg` for known paths or after a successful lookup with no
matches. Markdown source files are authoritative.
If configured QMD fails, report it to the user immediately and attempt repair.
If repair fails, pause knowledge-dependent work until the user approves a
fallback; never silently bypass broken QMD with `rg` or direct reads. Follow
the [search failure policy](docs/development-workflow.md#search-failures).

Follow the engineering policies linked below:

- Prefer fewer dependencies; justify additions by their concrete benefits
  under the [dependency policy](docs/development-workflow.md#third-party-dependencies).
- Cover regression fixes and functional changes with automated tests. Use
  [red-green TDD](docs/development-workflow.md#test-driven-development)
  when practical; explain exceptions. Test observable behavior through public
  interfaces, with fakes at external-system boundaries.
- Keep [test cost proportional](docs/development-workflow.md#test-cost-and-coverage)
  while preserving coverage, independence, and useful complete journeys.
- Keep [files cohesive](docs/development-workflow.md#file-organization);
  approximately 1,000 lines is a review threshold for source, tests, and styles.
- Keep [Markdown pages focused](docs/development-workflow.md#markdown-pages)
  on one topic or reader task, without numeric size limits.
- Isolate [validation inputs and output](docs/development-workflow.md#validation-checkout-isolation)
  to the active checkout.
- Declare supported [runtime and toolchain versions](docs/development-workflow.md#runtime-and-toolchain-versions)
  and keep development, CI, and deployment compatible.

Before pushing or merging to `main`, assess the complete delivery under the
[deployment policy](docs/deployment.md#deployment-decisions). Record a skip
decision only for functionally immaterial changes with no outstanding material
release. Full CI checks still run.

Run `bin/setup` after cloning. Choose checks for the changed files: use
`bin/check --documents-only` for Markdown edits and `bin/check` for foundation
checks only. Keep application tools out of both modes; run relevant application
checks explicitly for code edits.
Run `bin/check --full` locally after setup, test/build infrastructure changes,
or when focused checks leave material uncertainty. Require successful full
validation before merge or release. An enforced full CI gate can supply that
result for ordinary code changes; otherwise run the full check locally before
delivery. Do not run checks for discussion or read-only work. Batch edits
before checking; reuse passing results while relevant inputs are unchanged.
See [the workflow](docs/development-workflow.md#checks-and-project-extensions).
Use `bin/doctor` to inspect local setup and `bin/qmd-index` to refresh search
after uncommitted knowledge edits when current search results are needed.
Hooks refresh search after Git events.

Follow the [memory](memory/README.md) and [docs](docs/README.md) formats.
Keep accepted decisions separate from proposals. Preserve unrelated changes.
Keep secrets and generated caches out of Git.
