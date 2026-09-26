---
status: current
---

# Server data and API contract

This is the server v1 implementation reference. It implements the accepted
[product design](product-design.md) and [worker behavior](reporting-worker.md).
The AI worker remains a separate phase. The server stores instructions,
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
| `GET /newsroom` | Active reporters, worker contact, notices, and backup size; `?view=archive` shows removed/completed reporters. |
| `GET /newsroom/reporters/new` | Reporter form with schedule preview. |
| `GET /newsroom/reporters/{id}` | Settings, paginated stories, and paginated run/attempt history with instruction snapshots. |
| `POST /newsroom/reporters` | Create a reporter. |
| `POST /newsroom/reporters/{id}` | Save name, instructions, and schedule. |
| `POST /newsroom/reporters/{id}/{pause,resume,delete}` | Change reporter lifecycle. |
| `GET /newsroom/schedule-preview` | Preview a proposed schedule's first expected date. |
| `GET /newsroom/trash` | Recoverable articles and removal deadlines. |
| `POST /newsroom/articles/{id}/{delete,restore}` | Move an article to Trash or restore it. |

Schedule form fields are `cadence` (`daily`, `weekly`, `monthly`, `once`),
repeated `weekdays` (`mon` through `sun`), `day_of_month` (1–31), and `date`.
Only fields relevant to the chosen cadence apply. Owner history accepts
`page` for runs and `articles_page` for stories. There is no Run Now, article
editor, per-reporter model selection, reassignment, or feedback inbox.

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
| `GET /articles/{id}` | Retrieve a complete retained article. |

### Daily discovery and claims

A check-in returns `reporting_date` and `runs` (possibly empty). Each run
contains its ID, reporter configuration, original expected date, kind, state,
`late`, and any `current_attempt` ID/expiry. A fresh daily request ID records
contact even when no assignment is due. Replaying an old request ID does not
create a new contact date. The work list reflects current state on each fetch.

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
research allowance. Changed contractor instructions reopen a failed assignment
with a new bounded generation, retaining its due date and earlier attempts.

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
its reporter attribution. A completed contractor leaves the active roster only
after publication or a successful empty result.

If a contractor resumes before its pause acknowledgment arrives, the server
records that acknowledgment and reoffers the same assignment for research.
Replaying the acknowledgment returns its receipt without changing the new attempt.

Success returns `run_id`, `submission_id`, `outcome`, and `article_ids`. The
server saves this receipt and a canonical payload hash in the same transaction.
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
justifies it. There is no embedding or AI search service.

History and search default to 30 rows, allow 1–100, and return `page`, `limit`,
`total`, and `has_more`. Page numbers are bounded to 1–100,000. Articles sort by
publication time then ID descending; runs by expected date then ID descending.
Concurrent publication can shift offset-based pages; this is not an archive
snapshot protocol. Deleted articles are absent from search and retrieval.

Errors are JSON `{"error":"stable_code","message":"Explanation"}`. HTTP status:
401 invalid/missing authentication; 403 wrong role or ownership; 404 missing
record; 409 state/idempotency conflict; 413 too large; 415 wrong media type;
422 invalid payload. Invalid JSON syntax is 400. A validation failure never
partially publishes. Do not log tokens or complete request bodies.

## Calendar, pause, and deletion behavior

New schedules and edits activate tomorrow in Pacific Time; today's old
assignment remains. Monthly schedules clamp to the month's last day while
retaining the selected day for later months. Recurring and one-time categories
cannot be interchanged. A contractor date can change before it is due. Once
its due day arrives, the date stays fixed; its instructions can still change.

Discovery combines missed, unstarted recurring assignments into one current
catch-up. It retains old rows as `superseded` and links them to that run. An
active attempt takes precedence. Each current recurring occurrence has its own
retry allowance. Failed completed occurrences stay in history; the next normal
occurrence can proceed. No catch-up operation infers a coverage span.

Pausing prevents new research but keeps daily worker contact meaningful.
Acknowledged recurring occurrences stay skipped. A paused contractor retains
one unfinished assignment; resume reoffers that original run. An overdue
contractor never expires automatically.

An entire due day is allowed. A run is late at the next Pacific midnight,
including daylight-saving changes. Maintenance runs independently of browsers
and workers. See [operations](server-operations.md#monitoring-and-email) for
outage grouping and email retry behavior.

Moving an article to Trash hides it immediately. Restore is allowed for 30
elapsed days (720 hours), using the same ID and publication timestamp.
Maintenance then removes its content from the live database. Run history and
content-free receipts stay. SQLite secure deletion is enabled; retained
backups can still contain old content until they age out. No separate search
index or image store needs purging.
