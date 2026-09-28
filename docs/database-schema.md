---
status: current
---

# Database schema

This is the accepted SQLite schema baseline for the server, approved on
September 25, 2026 as currently understood. It implements the accepted
[product design](product-design.md) and [worker boundary](reporting-worker.md).
The owner agreed with the enumerated six-table schema; no further reason was
stated. It separates expected work, attempts, published content, and monitoring
so retries and reporter removal preserve history. The tradeoff is additional
operational records alongside the articles.

The baseline is implemented in [version 1 SQL](../news/schema.sql). Its detailed
constraints, indexes, and additional operational fields are engineering choices.
[Migration 2](../news/migrations/002-archive.sql) adds article revisions and a
single-row `archive_state` metadata table. Transactional triggers update these
tokens for the [archive synchronization protocol](server-contract.md#archive-manifest-protocol).
The [server contract](server-contract.md) specifies the implemented calendar,
claims, retry bounds, HTTP operations, and result payloads.

## Conventions

Use stable opaque text IDs, UTC timestamps for events, and ISO `YYYY-MM-DD`
dates for reporting days. Schedules use `America/Los_Angeles`; they contain
no execution hour. Enable SQLite foreign keys and use restrictive deletion
behavior. Removing a reporter or article first changes its lifecycle fields.
Article rows are permanently purged after the accepted 30-day Trash period;
reporter removal does not cascade into articles.

There are six application tables. Authentication configuration and the one
shared model do not require database tables in v1. Numbered migrations need
a small schema-version record in addition to these application tables.

## 1. Reporters

`reporters` holds the current instructions and schedule for each reporter.

| Column | Purpose |
| --- | --- |
| `id` | Stable reporter identity, retained after removal. |
| `name` | Current display name. |
| `prompt` | Full assignment and reporting instructions. |
| `schedule_json` | A validated daily, weekly, monthly, or one-time schedule. |
| `schedule_effective_date` | Pacific date from which the saved schedule generates occurrences. |
| `paused` | Boolean flag; pausing does not cancel work already underway. |
| `config_version` | Integer incremented when editable configuration changes. |
| `created_at`, `updated_at` | Server-recorded lifecycle timestamps. |
| `deleted_at` | Nullable time of owner removal. |
| `completed_at` | Nullable time all contractor dates were satisfied, with no future dates remaining. |

A reporter is on the active roster while both `deleted_at` and `completed_at`
are null. Paused reporters remain on that roster. A completed contractor and
an owner-deleted reporter stay distinguishable. Articles keep their original
reporter ID.

Schedule objects:

```json
[
  {"cadence": "daily"},
  {"cadence": "weekly", "weekdays": ["mon", "thu"]},
  {"cadence": "monthly", "day_of_month": 15},
  {"cadence": "once", "dates": ["2026-10-01", "2026-10-03"]}
]
```

Each reporter stores one such object. A one-time schedule identifies a
contractor without a separate reporter type field. Under the accepted
[category rule](product-design.md#recurring-reporters-and-one-time-contractors),
reject edits crossing between `once` and any recurring cadence. Permit changes
among daily, weekly, and monthly schedules. Keep the chosen monthly
`day_of_month` unchanged. Under the accepted
[monthly scheduling rule](product-design.md#schedules-by-day), generate an
occurrence on the last day of a month when the chosen day does not exist.

The [contractor date-list extension](contractor-schedules.md) reads legacy
`{"cadence":"once","date":"2026-10-03"}` objects as one-element lists.
It needs no new schema version and does not rewrite stored attempt snapshots.
Each scheduled date still has its own run. A successful later run satisfies
earlier dates while their original failed or superseded outcomes remain.
Completion is derived from successful run dates; API history exposes a separate
`satisfied_by_run_id` value without changing stored failures into successes.

The `schedule_effective_date` field is an engineering addition for the accepted
[schedule activation rule](product-design.md#schedules-by-day). Set it to
tomorrow on creation or schedule change. Before replacing an existing schedule,
materialize its due occurrences through today in the same transaction, so
today's assignments and missed history remain intact. Generate future
occurrences from the replacement schedule starting on its effective date.
Ordinary prompt edits do not change that date. Do not use it as a research
coverage boundary.

## 2. Runs

`runs` records each expected reporting occurrence, including ones the worker
never starts. It allows the server to detect missing results independently of
article creation or worker contact.

| Column | Purpose |
| --- | --- |
| `id` | Stable assignment ID issued by the server. |
| `reporter_id` | Foreign key to the original reporter. |
| `expected_date` | Pacific calendar date when a result is expected. |
| `kind` | `scheduled` or `catch_up`. |
| `state` | Current execution state or final outcome. |
| `created_at`, `finished_at` | Creation time and nullable terminal time. |
| `retry_not_before` | Nullable earliest time another attempt may start. |
| `retry_generation` | Integer identifying the current bounded retry allowance. |
| `superseded_by_run_id` | Nullable link from missed work to its replacement catch-up run. |
| `closed_reason` | Nullable explanation for cancellation or supersession. |

Make `(reporter_id, expected_date)` unique. Repeated discovery or maintenance
must reuse the same occurrence. One catch-up run can replace several missed
occurrences without changing their histories to successful outcomes.

Run states: `pending`, `running`, `retry_wait`, `published`,
`nothing_to_publish`, `skipped_paused`, `failed`, `superseded`, and `cancelled`.
`published`, `nothing_to_publish`, `failed`, `superseded`, and `cancelled` are
terminal under the current retry allowance. A contractor's final retained date
can reopen
under the accepted [instruction-edit recovery rule](product-design.md#recurring-reporters-and-one-time-contractors).
`skipped_paused` closes a recurring occurrence,
but suspends an unfinished contractor's assignment. Under the accepted
[resume behavior](product-design.md#pausing-reporters), that contractor's same
run returns to `pending` on resumption, then can join a later catch-up. Its prior pause attempt remains in
history; the eventual research uses a new attempt. Keep `finished_at` null
while the contractor's assignment is suspended. Neither a pause acknowledgment
nor resumption completes the contractor.

Engineering bookkeeping for instruction-edit recovery: increment
`retry_generation` only when changed instructions reopen an exhausted
contractor's unresolved assignment. Dates satisfied by later success cannot
reopen. Set the same run back to `pending`, clear its terminal timestamp,
and preserve its original due date, attempts, and errors. Prior failure times
remain in the attempts and incidents. Renaming, ordinary polling, unchanged
instruction saves, and pause acknowledgments cannot reset the retry budget.

Lateness is calculated from the expected day and received outcome; it is not
a competing run state. A run can be both running and late. No research
coverage dates are calculated or stored on the run.

## 3. Run attempts

`run_attempts` records attempts to complete a run. A retry creates another
attempt under the same run, preserving failures and the instructions used.
Under the accepted [start and recovery behavior](reporting-worker.md#starting-work-and-recovering-after-a-crash),
the server creates this record when the worker announces it is starting,
before research begins. No article row exists until a result is accepted.

| Column | Purpose |
| --- | --- |
| `id`, `run_id` | Attempt identity and parent run. |
| `attempt_number` | Increasing number, unique within its run. |
| `retry_generation` | The run's retry allowance when this attempt started. |
| `worker_id` | Logical identity obtained from authentication. |
| `config_snapshot_json` | Name, full prompt, schedule, pause flag, and configuration version supplied when claimed. |
| `started_at`, `finished_at` | Server-recorded attempt times. |
| `claim_token_hash`, `claim_expires_at` | Proposed ownership and recovery fields; never store the raw token. |
| `outcome` | Nullable `published`, `nothing_to_publish`, `skipped_paused`, or `failed`. |
| `reason` | Explanation for an empty or skipped result. |
| `error_code`, `error_message`, `retryable` | Failure details and retry classification. |
| `submission_id`, `payload_hash`, `receipt_json` | Nullable result-delivery record for safe retries. |

Use unique `(run_id, attempt_number)` and `(worker_id, submission_id)` keys.
A repeated submission with the same content returns its stored receipt. A
different payload using the same submission ID is a conflict. This must not
recreate articles, send another logical alert, or restore deleted content.

Permit only one open attempt per run and one successful research outcome
(`published` or `nothing_to_publish`) per run. Pause acknowledgments are not
successful research and must not block a resumed contractor's later result.
Run-state validation prevents reopening skipped recurring occurrences.
Claiming work also serializes research for each reporter. Validate state
and write the outcome, articles, receipt, and contractor completion in one
transaction. Malformed submissions leave the attempt unfinished and publish
nothing. Server-detected abandoned attempts retain a distinct error code.

Count research attempts within the current retry generation to enforce its
budget; pause acknowledgments do not consume research attempts. Attempt numbers
continue increasing across generations. The generation fields are engineering
additions for the accepted instruction-edit recovery rule, not permission for
the worker to grant itself more retries.

The [claim protocol](server-contract.md#daily-discovery-and-claims) defines
ownership, explicit replacement, retry bounds, and late delivery. Deletion
does not revoke valid work already underway. A replaced attempt cannot
publish new work. No attempt contains a model field or inferred coverage.

## 4. Articles

`articles` stores the durable published output independently of its HTML
presentation and the reporter's current lifecycle.

| Column | Purpose |
| --- | --- |
| `id` | Stable article identity and URL key. |
| `reporter_id` | Original reporter; never reassigned in v1. |
| `attempt_id` | The accepted attempt that produced this article; its run is available through that relationship. |
| `reporter_name` | Attribution snapshot, taken from the attempt's configuration. |
| `title`, `summary` | Worker-supplied plain text. |
| `body_markdown` | One Markdown body, including inline links and external image URLs. |
| `sources_json` | Worker-supplied array of source titles and URLs. |
| `article_date` | Worker-supplied date for the report. |
| `coverage_start`, `coverage_end` | Worker-supplied dates describing what the article covers. |
| `published_at` | Server time when the submission is committed and becomes public. |
| `deleted_at` | Nullable time of recoverable removal. |

The article's reporter must match the reporter of its producing run. The
server sets these relationships from the authenticated attempt rather than
trusting attribution fields in the article payload. A run may publish several
articles, each with a different supplied coverage span.

The date contract requires `article_date` and both coverage dates as
ISO calendar dates. Treat coverage endpoints as inclusive, allow a single-day
span, and reject an end before its start. Future spans are valid, including a
weekend planner published on Thursday. Timeless content or finer precision
would require a later change to this calendar-date contract.

The server checks format and ordering only. It never selects, fills in, or
advances coverage from the schedule, article date, publication timestamp,
prompt, or run history. Archive filters compare the supplied dates directly.
An empty result creates no article and no invented coverage metadata.

Use `published_at` and `id` for stable newest-first ordering. Restoring an
article clears `deleted_at` without changing its ID, body, dates, or original
publication time. Exclude deleted articles from public views and worker
archive retrieval. No source or image table is needed: source metadata belongs
to its article, and images remain on external hosts.

Under the accepted [30-day Trash rule](product-design.md#independent-article-lifecycle),
purge the article row and derived search entries when its deletion is at least
30 elapsed days old. Keep its parent attempt and original submission receipt,
including the article ID and payload digest, without retaining the article
payload in that receipt. An identical delivery retry still returns the receipt
and never inserts the purged article again. A receipt can therefore refer to
an article ID whose content no longer exists.

Proposed implementation: index `deleted_at` for periodic cleanup, use UTC
timestamps for the 30-day interval, and reject restoration at or after the
deadline even if the next cleanup pass has not run yet. Restore and purge must
check the current row in a transaction so they cannot race into resurrection.

## 5. Worker check-ins

`worker_checkins` records daily work discovery, including days with no work.

| Column | Purpose |
| --- | --- |
| `id`, `worker_id` | Record identity and authenticated logical worker. |
| `request_id` | Client-generated ID for safely retrying the discovery request. |
| `received_at` | Server receipt time. |
| `checkin_date` | Pacific calendar date of that receipt. |

Make `(worker_id, request_id)` unique. A retried request reuses its check-in;
assignment discovery can still return the current eligible work. A check-in
does not complete any run. The worker identity and monitoring start date can
be deployment configuration for v1; no machine registry or worker-management
UI is required.

## 6. Incidents

`incidents` supports newsroom warnings and notification delivery without
creating a separate email queue service.

| Column | Purpose |
| --- | --- |
| `id`, `incident_key` | Record identity and unique key for one logical incident. |
| `kind` | For example, missing worker contact, overdue run, exhausted failure, or invalid reporting after reporter deletion. |
| `reporter_id`, `run_id`, `worker_id` | Nullable references identifying what is affected. |
| `message` | Owner-readable explanation, without credentials. |
| `first_seen_at`, `last_seen_at`, `resolved_at` | Observation times and nullable resolution time. |
| `notification_sent_at` | Nullable time email delivery was acknowledged. |
| `notification_attempts`, `notification_retry_at`, `notification_error` | Delivery retry state. |

Repeated observations update an existing incident instead of creating another
logical alert. Follow the accepted
[alert grouping policy](reporting-worker.md#alert-grouping): one incident email
per continuous worker outage, no daily reminders or separate missing-run emails
for that outage, and individual exhausted-run alerts while the worker is
communicating. Keep affected runs visible independently of notification grouping.

Email is sent outside database transactions through the selected
[Resend delivery](implementation-design.md#email-delivery). The [operations guide](server-operations.md#monitoring-and-email) specifies
incident resolution and the bounded retry window after an ambiguous send.
The SQL includes frozen payloads, first-attempt times, and provider receipts.

## Relationships and indexes

One reporter has many runs; one run has many attempts; a successful attempt
has zero or many articles. Articles also retain the reporter ID directly for
attribution and archive filtering. Worker check-ins are independent of runs.
Incidents can reference a run, a reporter, or the configured worker.

In addition to primary and unique keys, start with indexes for visible articles
by `(published_at, id)` and `(reporter_id, published_at, id)`, runs by
`(state, expected_date)`, check-ins by `(worker_id, received_at)`, and pending
incident delivery. Add archive search indexes after choosing the text search
implementation and checking its query plans. All of these are ordinary local
queries; none require AI execution on the server.
