# Documents

Store designs, decisions, research, and reference guides here. Use
[memory](../memory/README.md) for durable guidance and non-derivable context.
Use [td](task-tracking.md) for local progress and handoffs, and GitHub Issues
for shared scope and acceptance criteria.

## Page format

Every ordinary document has a clear title, an opening summary, and one
status field:

```yaml
---
status: current
---
```

Use `draft` for a document still being developed, `current` for the current
reference or plan, `superseded` when another document replaces it, and
`archived` when it is no longer active. A current design does not prove it
has been implemented or approved. Keep superseded and archived documents
under `archive/`, with a replacement link when one exists.

Frontmatter uses one-line string values. These checks accept plain text,
JSON-style double quotes, or YAML single quotes. Only `status` is defined
for ordinary docs. README indexes do not need frontmatter. Extend the schema
deliberately if the project needs additional fields.

## Decisions and evidence

Record each accepted decision in its authoritative document before moving
to the next interview question. Include the date, the user's reason or an
established constraint, and a material tradeoff when it explains the choice.
State that a reason is unknown when it is unknown. Keep recommendations,
unanswered questions, and accepted decisions separate. Silence is not approval.

Use sources and verification dates for changing external facts when useful.
Review those facts when related work depends on them. Keep each decision in
one place and link to it elsewhere. When it changes, explain what supersedes
the old decision. Do not store interview transcripts or task checklists here.

## Organization and links

Keep each page focused on one topic or reader task. Review long pages before
extending them, and move independent topics into linked pages when useful.
Preserve decision reasons and evidence. Follow the
[Markdown guidance](development-workflow.md#markdown-pages).

Keep small projects flat. Add `initiatives/` or `research/` when needed.
Link every active page from this index, directly or through another README
index. Remove archived pages from active indexes. Use relative Markdown file
links and ordinary Markdown heading anchors. Standard ATX and setext headings,
duplicate heading slugs, and explicit HTML `id` anchors are supported.

Generated docs can be excluded through `checks.exclude` in
`.config/knowledge.json`. Align QMD exclusions when they should not be
searched. Do not exempt hand-written pages merely to bypass failed checks.

## Active pages

- [Local task tracking](task-tracking.md): td setup, progress, handoffs, review, and local data.
- [Concept](concept.md): the draft idea for a personal AI news agency.
- [Product design](product-design.md): accepted product decisions and open
  questions for the first useful version.
- [Contractor assignment dates](contractor-schedules.md): finite date lists,
  catch-up, completion, retained failures, and retry recovery.
- [Upcoming reporting calendar](newsroom-calendar.md): unified newsroom dates,
  Pacific month navigation, lifecycle rules, and accessible layouts.
- [Implementation design](implementation-design.md): server-first implementation
  sequence, selected stack, deployment context, and remaining technical choices.
- [Backups](backups.md): encrypted recovery snapshots, retention, restore
  checks, and email warnings when backup storage exceeds 1 GB.
- [Server contract](server-contract.md): implemented records, Markdown article
  payloads, browser routes, worker API, and submission validation.
- [Server operations](server-operations.md): local setup, validation, release
  prerequisites, monitoring, backups, and recovery.
- [Local failure notifications](failure-alerts.md): immediate macOS alerts for
  final reporter failures and local worker errors.
- [Automatic deployment](deployment.md): main-branch releases, deployment
  credentials, migrations, maintenance, and failure handling.
- [Database schema](database-schema.md): accepted table and field baseline,
  relationships, and worker-supplied article coverage metadata.
- [Reporting worker](reporting-worker.md): newsroom API boundary, shared Claude Code
  engine selection, run outcomes, and overdue-work detection.
- [Worker operations](worker-operations.md): Claude Code implementation, private
  configuration, recovery, tests, and required after-merge LaunchAgent installation.
- [Article history search](article-history-search.md): semantic retrieval,
  shared batch snapshots, local QMD setup, and retrieval checks.
- [Pi research extension comparison](worker-research-comparison.md): package
  tradeoffs, provider pricing, and evidence for the first worker trial.
- [Search service evaluation](search-evaluation.md): controlled reporting prompts,
  provider trials, and source-based assessment.
- [Codex worker evaluation](worker-codex-evaluation.md): GPT-6 Luna through the
  existing Pro subscription, compared with the local Qwen reporting runs.
- [Sleep and fitness writing comparison](worker-writing-evaluation.md): shared
  research, Sol/Qwen/Hemmingway drafts, measured runtimes, factual review, and
  evidence for retaining the current Sol approach.
- [Codex research additions](worker-research-addons.md): reader, literature,
  discussion, and browser tools that could complement built-in web search.
- [Evaluation reports](evaluations/README.md): preserved candidate outputs from
  the search pilot, including known errors for comparison.
- [Reporting examples](reporting-examples.md): concrete assignments and proposed
  evaluation cases for the reporting engine.
- [Development workflow](development-workflow.md): setup, search, hooks,
  worktrees, diagnostics, dependency choices, testing, and checks.
