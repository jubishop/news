# News project instructions

Read the [concept](docs/concept.md) for the project's direction and the
[implementation design](docs/implementation-design.md) for the selected
Python, Flask, and SQLite stack. Read the [server contract](docs/server-contract.md)
and [operations guide](docs/server-operations.md) for server v1. Read [worker operations](docs/worker-operations.md) for the vanilla Codex worker
and its required after-merge commissioning.

The user is in Pacific Time. Use PST/PDT unless asked otherwise. The user's
default shell is fish. Use short, direct sentences and ASD-STE100 Simplified
Technical English principles. Explain necessary technical terms and provide
enough context to understand decisions.

Keep durable guidance and non-derivable context in [memory](memory/README.md).
Keep designs, decisions, and research in [docs](docs/README.md). Use the
[GitHub Issues](https://github.com/jubishop/news/issues) for work items and
implementation progress.

Write durable memory only to user-managed containers. Use this repository's
`memory/` for repository facts. For cross-project facts, check existing notes
in `~/memory/`, update the relevant topic page, and maintain its `README.md`
index. Never write memory to an agent-specific, hidden, or internal store.
Do not record transient task state as durable memory.

Minimize GitHub API requests. Fetch collections in batches with `gh issue
list`, `gh pr list`, `gh api --paginate`, or bounded GraphQL queries. Request
only needed fields and pages, and reuse results. Do not fetch each issue or
pull request separately when a collection query can supply the same data.

Before non-trivial work or writing memory, search the relevant knowledge.
Use `bin/knowledge search "term"` for known terms and
`bin/knowledge query "question" --no-rerank` for broader questions.
Read focused results with `bin/knowledge get <path> -l 80`.
Use direct reads or `rg` for known paths or after a successful lookup with no
matches. Markdown source files are authoritative. Update existing pages when possible.
If configured QMD fails, report it to the user immediately and attempt repair.
If repair fails, pause knowledge-dependent work until the user approves a
fallback; never silently bypass broken QMD with `rg` or direct reads. Follow
the [search failure policy](docs/development-workflow.md#search-failures).

Prefer fewer third-party dependencies. Use standard libraries, platform APIs,
or a focused implementation owned by the project when they meet its needs at
a reasonable maintenance cost. Add a dependency when its concrete benefits
justify it; initial implementation convenience alone is not enough. Apply
the [dependency policy](docs/development-workflow.md#third-party-dependencies)
through ordinary technical judgment, without a separate approval step.

Regression fixes and functional changes require automated tests for the
changed behavior. Use red-green test-driven development (TDD) whenever
practical: prove a focused test fails before implementation and passes after.
If testing first is not practical, explain why and how the behavior was
verified. Follow the [testing workflow](docs/development-workflow.md#test-driven-development).

Test user-visible outcomes, public interfaces, and interactions with external
systems. Put fakes at external-system boundaries so real project logic runs.
Do not test private helpers or internal structure, expose private functionality,
or add production APIs only for tests. Tests should allow internal refactoring
that preserves behavior.

Prepare unrelated test prerequisites through isolated fixtures or existing
public interfaces. Use the least costly test level that proves the required
behavior, retaining complete journeys and interaction-specific coverage.
Measure before adding parallel execution and preserve test independence.
See [test cost and coverage](docs/development-workflow.md#test-cost-and-coverage).

Keep files focused on one coherent responsibility. Use approximately 1,000
lines as a review threshold for hand-written source, tests, and styles, not
a hard cap. Prefer cohesive extraction; do not compress formatting or create
arbitrary fragments to meet a count. Larger files are acceptable when splitting
would reduce clarity. See [file organization](docs/development-workflow.md#file-organization).

Keep memory, docs, and other Markdown pages focused on one topic or reader
task. When extending a long page, review its scope and split independent
topics into linked pages when that improves reading and maintenance. Use
the [Markdown guidance](docs/development-workflow.md#markdown-pages), without numeric size thresholds.

Scope project source discovery and mutable validation output to the active
checkout. Exclude nested worktrees and temporary copies; include required
generated inputs deliberately. `.gitignore` does not control every tool's
discovery. Follow [checkout isolation](docs/development-workflow.md#validation-checkout-isolation).

Declare supported runtime and toolchain versions and keep development, CI,
and deployment compatible with that policy. Application commands should reject
unsupported versions before work starts. Prefer maintained releases and
coordinate upgrades. See [runtime and toolchain versions](docs/development-workflow.md#runtime-and-toolchain-versions).

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

Read the relevant memory or docs index for its format and maintenance rules.
Keep accepted decisions separate from proposals. Preserve existing project
instructions, setup commands, hooks, and unrelated changes when adapting this
foundation. Keep secrets and generated caches out of Git.
