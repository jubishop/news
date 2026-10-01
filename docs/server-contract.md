---
status: current
---

# Server data and API contract

This is the server v1 implementation reference. It implements the accepted
[product design](product-design.md) and [worker behavior](reporting-worker.md).
The separate [Codex worker](worker-operations.md) uses this API. The server stores instructions,
assignments, outcomes, and articles; it never performs research or selects a
model. See [operations](server-operations.md) for setup and deployment.

## Records and transactions

The six tables in the [schema baseline](database-schema.md) are implemented in
[version 1 SQL](../news/schema.sql): reporters, runs, run attempts, articles,
worker check-ins, and incidents. IDs are opaque strings. Event timestamps are
UTC Unix seconds; schedule dates use `America/Los_Angeles`.

SQLite uses WAL, foreign keys, a five-second busy timeout, and short write
transactions. `init-db` applies the initial numbered schema through
`PRAGMA user_version`; it rejects a database newer than the application.
Foreign keys restrict deletion. Removing a reporter retains its identity and
history. No operation cascades into articles.

Engineering fields beyond the baseline include a schedule materialization
cursor, an attempt's claim request ID and retry generation, and durable email
payload/delivery state. An attempt records a complete configuration snapshot.
There is no reporter or article model field and no server-maintained coverage
cursor. Each article retains the reporter name used when the attempt began.

Every claim or result is one transaction. Validation, publication of all
articles, receipt persistence, and successful contractor completion commit
atomically. Network requests and email delivery occur outside these writes.
The server accepts one logical worker identity and one unfinished attempt per
reporter. Reusing a removed reporter's ID for another reporter is unsupported.

## Access boundaries

The feed and article pages are public. `/newsroom` and descendants require the
owner's Cloudflare Access application. `/api` and descendants require a separate
worker application. Every origin request verifies the Access JWT's RSA
signature, issuer, audience, and expiry. The owner must match the configured
email. Worker tokens must contain a service identity (`common_name`).

The worker sends `CF-Access-Client-Id` and `CF-Access-Client-Secret` to Cloudflare.
Cloudflare supplies `Cf-Access-Jwt-Assertion` to the origin. News derives the
logical worker name from server configuration, so credential rotation does
not change its recorded identity. Browser and worker audiences are distinct;
neither grants the other's permissions. Direct requests with only an email
header, no JWT, or a forged JWT fail.

Owner mutations use POST, a signed session cookie, a CSRF token, and an Origin
check. CSRF is a check that another website cannot submit an owner's form.
Cookies are Secure, HttpOnly, and SameSite=Lax. Sessions expire after 12 hours.
The disposable browser fixture alone uses an HTTP cookie on loopback.

Responses prohibit caching and executable inline content. Raw HTML in Markdown
is escaped. Public pages do not expose prompts, failure detail, credentials,
or worker request payloads. `/health` is a minimal public database check.

## Article payload

```json
{
  "title": "Five ideas for the upcoming weekend",
  "summary": "A concise overview of the strongest options.",
  "article_date": "2026-09-24",
  "coverage_start": "2026-09-26",
  "coverage_end": "2026-09-27",
  "body_markdown": "## First option\n\nSee the [official event page](https://example.com/event).\n\n![A workshop](https://example.com/workshop.jpg)",
  "sources": [{"title": "Official event page", "url": "https://example.com/event"}]
}
```

All fields above are required. Unknown article fields are rejected. Title and
summary are plain text. `article_date`, `coverage_start`, and `coverage_end`
are exact ISO dates (`YYYY-MM-DD`). Coverage endpoints are inclusive and ordered;
future dates are allowed. No server timestamp determines research coverage.

### Inline images

The body supports CommonMark paragraphs, headings, emphasis, lists, quotes,
code, links, images, and tables. The Markdown renderer disables raw HTML and
unsafe URL schemes. Links and source URLs are absolute HTTP or HTTPS. Images
must use absolute HTTPS URLs; HTTP image syntax becomes alt text. Images load
lazily in the reader's browser without a referrer. News does not fetch, upload,
proxy, store, or back up images. Captions and credits can be ordinary Markdown.

Sources are structured title/URL pairs. An empty source list is permitted:
source sufficiency and inline citation placement belong to the assignment and
worker. Server validation cannot verify a claim or the quality of its research.

| Limit | Value |
| --- | --- |
| Request body | 2,000,000 bytes |
| Articles in a result | 1–20 for publication; zero otherwise |
| Title / summary | 300 / 2,000 characters |
| Markdown body | 250,000 characters per article |
| Sources | At most 100 per article |
| Source title / URL | 500 / 4,096 characters |
| Reporter name / instructions | 120 / 64,000 characters |
| Empty/pause reason or failure message | 4,000 characters |
| Client request/submission ID | 1–128 ASCII letters, digits, `_` or `-` |
| Ownership token | 32–256 characters; generate randomly |

## Browser routes

| Method and route | Purpose |
| --- | --- |
| `GET /` | Newest-first feed, search, reporter filter, pagination, and concise late-report status. |
| `GET /articles/{id}` | Full Markdown article and sources. |
| `GET /newsroom` | Upcoming reporting calendar, active reporters, worker contact, notices, and backup size; `?view=archive` shows removed/completed reporter cards. |
| `GET /newsroom/reporters/new` | Reporter form with schedule preview. |
| `GET /newsroom/reporters/{id}` | Settings, paginated stories, and paginated run/attempt history with instruction snapshots. |
| `POST /newsroom/reporters` | Create a reporter. |
| `POST /newsroom/reporters/{id}` | Save name, instructions, and schedule. |
| `POST /newsroom/reporters/{id}/{pause,resume,delete}` | Change reporter lifecycle. |
| `POST /newsroom/schedule-preview` | Preview a proposed schedule's first future date; legacy GET remains supported. |
| `GET /newsroom/trash` | Recoverable articles and removal deadlines. |
| `POST /newsroom/articles/{id}/{delete,restore}` | Move an article to Trash or restore it. |

The [reporting calendar](newsroom-calendar.md) accepts `month=YYYY-MM`, defaulting
to the current Pacific month. It projects active schedules without creating
runs and preserves today's saved assignments when schedules change.

Schedule form fields are `cadence` (`daily`, `weekly`, `monthly`, `once`),
repeated `weekdays` (`mon` through `sun`), `day_of_month` (1–31), and `dates`.
Contractor `dates` accepts repeated values or a list separated by whitespace
or commas. Dates must be distinct; there is no date-count cap. The legacy
single `date` field remains accepted when `dates` is absent. Saved contractor
schedules use `{"cadence":"once","dates":["2026-10-01","2026-10-03"]}`.
The newsroom uses individual native date pickers with **Add another** and
**Delete** controls. It submits repeated `dates` values, including hidden
retained due dates. Blank entries are ignored. See the
[date-entry guide](contractor-schedules.md#editing-dates).
Only fields relevant to the chosen cadence apply. For edits, preview accepts
`reporter_id` to validate retained due dates. Its `next_date` is the first future
date, or null when only due dates remain. Owner history accepts
`page` for runs and `articles_page` for stories. There is no Run Now, article
editor, per-reporter model selection, reassignment, or feedback inbox.

The newsroom posts preview fields with its CSRF token so long date lists do
not depend on URL-length limits. The existing form-body limit is 300,000 bytes;
the overall request limit is 2,000,000 bytes. Neither sets a fixed date count.

## Worker API

All routes below begin with `/api/v1/worker`. Send JSON for POST requests.
Store request IDs, ownership tokens, and completed results on the worker's
durable local storage before making the corresponding request.

| Method and route | Purpose |
| --- | --- |
| `POST /check-ins` | Record daily contact and discover relevant work. Body: `{"request_id":"unique-id"}`. |
| `POST /runs/{id}/claim` | Start or explicitly replace an attempt. |
| `POST /runs/{id}/renew` | Extend an unfinished attempt's ownership information. |
| `POST /runs/{id}/result` | Atomically submit a result and receive its receipt. |
| `GET /reporters/{id}/runs` | Paginated factual history, outcomes, errors, and attempt timestamps. |
| `GET /articles/search` | Search retained article text/metadata and supplied coverage dates. |
| `GET /articles/manifest` | Bounded ID/revision listing for consistent archive synchronization. |
| `GET /articles/{id}` | Retrieve a complete retained article, optionally guarded by archive `version`. |

### Daily discovery and claims

A check-in returns `reporting_date` and `runs` (possibly empty). Each run
contains its ID, reporter configuration, original expected date, kind, state,
`late`, and any `current_attempt` ID/expiry. A fresh daily request ID records
contact even when no assignment is due. Replaying an old request ID does not
create a new contact date. The work list reflects current state on each fetch.
Contractor runs also include `assignment_dates`: the unfinished dates included
in this execution. A catch-up keeps the latest included scheduled date as its
`expected_date`; it does not manufacture another daily retry allowance.

Claim body:

```json
{
  "request_id": "persisted-claim-id",
  "ownership_token": "a-worker-generated-cryptographically-random-token"
}
```

Use at least 32 random characters (for example `secrets.token_urlsafe(32)`).
The server stores only its SHA-256 hash. The reply contains `attempt_id`,
`attempt_number`, `ownership_token`, `claim_expires_at`, `acknowledgment_only`,
and the exact `reporter` snapshot to follow. Repeating the same request ID and
token recovers that reply after a lost response; conflicting reuse returns 409.
The snapshot is taken at claim time, so edits between discovery and claim apply.
For contractors the snapshot also contains `assignment_dates`. These dates
are scheduling context, not a research coverage interval. The existing worker
passes the exact snapshot to research without a separate installation change.

Ownership information lasts six hours and can be renewed with `attempt_id`
and `ownership_token`. Expiry alone does not discard work or make a second
attempt available. A valid unreplaced attempt can still submit after expiry,
pause, or reporter removal. This protects completed local research from loss.

After a crash, deliver saved completed results first. To abandon unfinished
work, claim with a new request ID and token plus `replace_attempt_id` naming
the current attempt. Replacement is explicit and limited to the same worker
and run. It records the abandoned attempt as failed. The old token then cannot
publish a new result. Replaying an already accepted result still returns its
receipt. Replaying an old claim returns its old snapshot, not a new attempt.

Research permits three attempts per run/retry generation. A retryable reported
failure waits 15 minutes before another claim; a deliberate crash replacement
can proceed immediately. Exhaustion or `retryable:false` closes the run and
opens an incident. Paused acknowledgment-only attempts do not spend this
research allowance. Changed contractor instructions reopen only the final
retained date when its run has failed, with a new bounded generation. Earlier
failed dates wait for later work, including a future date or an active run;
they keep their outcomes and are included in the later run's scope. Original
due dates and attempts remain.
A later scheduled contractor run has its own allowance. Its success satisfies
earlier failed dates, including exhausted ones. Repeated checks alone never
replenish an exhausted allowance, and satisfied failures never reopen.

### Results and receipts

```json
{
  "submission_id": "persisted-result-id",
  "attempt_id": "server-issued-attempt-id",
  "ownership_token": "the-token-used-to-claim",
  "outcome": "nothing_to_publish",
  "articles": [],
  "reason": "No useful new material for this assignment."
}
```

| Outcome | Additional fields and effect |
| --- | --- |
| `published` | One or more valid `articles`; all publish immediately. |
| `nothing_to_publish` | Empty articles and required `reason`; successful completion. |
| `skipped_paused` | Empty articles and required `reason`; acknowledge a pause without research success. |
| `failed` | Empty articles and `error:{"code":"research_failed","message":"Explanation","retryable":true}`. |

An acknowledgment-only claim accepts only `skipped_paused`. A research attempt
started before a pause may still finish its research. A result cannot change
its reporter attribution. A contractor leaves the active roster only when
all retained assignment dates are satisfied by publication or successful empty
results and no future dates remain. Earlier failed outcomes remain in history.

If a contractor resumes before its pause acknowledgment arrives, the server
records that acknowledgment and reoffers the same assignment for research.
Replaying the acknowledgment returns its receipt without changing the new attempt.

Success returns `run_id`, `submission_id`, `outcome`, `article_ids`, and
`run_state`. The last field records the run state at acceptance, distinguishing
`retry_wait` from final `failed` for immediate local worker notifications. The
server saves this receipt and a canonical payload hash in the same transaction.
Replayed receipts retain their original state; older receipts can omit
`run_state`. This field does not describe later run transitions.
Identical delivery retries return it without republishing. Different content
under the same submission ID is a conflict. Later requests cannot amend a
published result. Receipt retention prevents retries from restoring deleted
or permanently purged articles.

Removing a reporter cancels unstarted work. A pre-removal active attempt may
still deliver. A new claim or new work after removal returns a conflict and
opens a deduplicated invalid-reporting notice. Authentication failures do not
create incidents, and harmless accepted-result retries do not create notices.

### Search, history, and errors

Article search accepts `q` (up to 300 characters), `reporter_id`, `coverage_start`,
`coverage_end`, `page`, and `limit`. Coverage filters match overlapping inclusive
spans supplied by workers. Search uses literal SQL `LIKE` over title, summary,
and body, with parameters and escaped wildcards. This intentionally avoids
another index for the initial small archive; add an index when measured load
justifies it. There is no server-side embedding or AI search service. The worker
builds its own [semantic history index](article-history-search.md) using the
manifest protocol below. Search remains available for bounded ad hoc requests.

History and search default to 30 rows, allow 1–100, and return `page`, `limit`,
`total`, and `has_more`. Page numbers are bounded to 1–100,000. Articles sort by
publication time then ID descending; runs by expected date then ID descending.
Concurrent publication can shift offset-based pages; this is not an archive
snapshot protocol. Deleted articles are absent from search and retrieval.
Contractor history includes nullable `satisfied_by_run_id`, identifying the
successful run that satisfied that date independently of its original outcome.

Errors are JSON `{"error":"stable_code","message":"Explanation"}`. HTTP status:
401 invalid/missing authentication; 403 wrong role or ownership; 404 missing
record; 409 state/idempotency conflict; 413 too large; 415 wrong media type;
422 invalid payload. Invalid JSON syntax is 400. A validation failure never
partially publishes. Do not log tokens or complete request bodies.

### Archive manifest protocol

`GET /articles/manifest` returns `articles:[{id,revision}]`, `version`, `page`,
`limit`, `total`, and `has_more`. It contains no article text. The default limit
is 100; allowed limits are 1–100 and pages are 1–100,000. Retained articles sort
by publication time and ID descending. Empty archives return an empty first page,
`total:0`, and `has_more:false`.

Article revisions and the archive version are opaque 32-character lowercase
hexadecimal tokens. [Schema migration 2](../news/migrations/002-archive.sql)
initializes them for existing data. SQLite triggers change revisions on article
insertion or updates to identity, reporter attribution, title, summary, body,
sources, dates, publication order, or Trash state. These changes and purge also
change the archive version in the same transaction. Reporter profile edits do
not change stored historical attribution. The tokens are equality checks, not
timestamps or sequence numbers.

Start with page 1 without `version`. Send its returned version with every later
page and each `GET /articles/{id}?version=...` request. Pages after the first
require a version. Each request checks the version and reads its result in one
SQLite read transaction. A mismatched version returns HTTP 409 with
`error:archive_changed`; a malformed version returns 422. Article retrieval
returns its `revision` and excludes Trash. Retrieval without a version retains
the existing behavior.

After validating all pages and any downloaded bodies, request manifest page 1
with the same version and `limit=1` as a final consistency check. Verify the
version and total again, including for an empty archive. A conflict requires a
fresh listing, never deletion based on an incomplete one. The worker allows three
attempts, preserves its last valid cache on preparation failure, and serves no
stale fallback. Server writers remain free to commit; the protocol detects changes
instead of holding a database transaction open across HTTP requests. Later changes
wait for the next batch. See [worker recovery](article-history-search.md#private-state-and-recovery).

## Calendar, pause, and deletion behavior

New schedules and edits activate tomorrow in Pacific Time; today's old
assignment remains. Monthly schedules clamp to the month's last day while
retaining the selected day for later months. Recurring and contractor categories
cannot be interchanged. Contractor future dates can be added, edited, or removed.
Each new date must be after today. Once a date is due, it stays fixed; instructions
can still change. Old single-date schedules and attempt snapshots remain valid.

Discovery combines missed, unstarted recurring assignments into one current
catch-up. It retains old rows as `superseded` and links them to that run. An
active attempt takes precedence. Each current recurring occurrence has its own
retry allowance. Failed completed occurrences stay in history; the next normal
occurrence can proceed. No catch-up operation infers a coverage span.

Contractor discovery combines unfinished due dates, including today when
scheduled, under the latest eligible scheduled run. It retains superseded
rows and failed attempts. Failed runs keep their outcomes even when later
success satisfies their dates. An active attempt keeps its scope; dates that
become due while it runs wait. A successful run satisfies all scheduled dates
through its original expected date. Future dates remain pending. See the
[contractor rules](contractor-schedules.md) for examples and recovery.

Pausing prevents new research but keeps daily worker contact meaningful.
Acknowledged recurring occurrences stay skipped. A paused contractor retains
unfinished assignments; resume combines due dates under the catch-up rule.
An overdue contractor never expires automatically.

An entire due day is allowed. A run is late at the next Pacific midnight,
including daylight-saving changes. Maintenance runs independently of browsers
and workers. See [operations](server-operations.md#monitoring-and-email) for
outage grouping and email retry behavior.

Moving an article to Trash hides it immediately. Restore is allowed for 30
elapsed days (720 hours), using the same ID and publication timestamp.
Maintenance then removes its content from the live database. Run history and
content-free receipts stay. SQLite secure deletion is enabled; retained
backups can still contain old content until they age out. No separate server
search index or image store needs purging. The worker's local history index
reconciles deletions at its next successful batch refresh.
