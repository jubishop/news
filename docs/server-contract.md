---
status: draft
---

# Server data and API contract

This is the proposed implementation contract for the VPS server. It translates
the accepted [product design](product-design.md) and
[worker behavior](reporting-worker.md) into records, routes, and validation
rules. It is a design, not implemented code or a claim that every technical
detail has received owner approval. Build this server and a deterministic test
client before the local research worker, following the
[implementation sequence](implementation-design.md#implementation-sequence).

## Design conventions

- Use one Flask application and one authoritative SQLite database on the VPS.
  Keep HTTP handlers separate from database transactions and schedule logic.
- Give reporters, runs, attempts, and articles stable opaque IDs. Use UTC
  timestamps for recorded events and Pacific calendar dates for schedules.
  No reporter or article has a configurable model field.
- Keep the public reading routes separate from owner management routes and
  the authenticated worker API. Public page rendering reads the database
  directly; it does not need a public JSON API.
- Prefer ordinary synchronous requests and a short periodic server maintenance
  command. Research, model calls, and AI summaries remain worker responsibilities.

These are engineering choices intended to keep the first server small. They
avoid a separate database service, queue service, or browser application while
preserving a clear interface for the later worker.

## Record model

The accepted [database schema baseline](database-schema.md) enumerates six
application tables and their fields. This summary defines their responsibilities
rather than final SQL migrations. Exact API and protocol choices remain
proposals where identified.

| Record | Principal fields and constraints |
| --- | --- |
| Reporter | Stable ID, display name, prompt, schedule, configuration version, pause flag, creation/update times, and optional removal/completion times. Retain the record after removal for attribution and valid incoming work. |
| Scheduled run | ID, reporter ID, expected reporting date, state, optional catch-up relationship, and eventual completion time. Make `(reporter_id, expected_date)` unique so repeated maintenance or work requests cannot create the same occurrence twice. |
| Attempt | ID, run ID, authenticated worker identity, claim/start time, ownership/expiry data, prompt and configuration snapshot, outcome or error, and result receipt. Keep failed attempts separate from the logical run so retries preserve history. |
| Article | ID, attempt ID, original reporter ID and name, title, summary, Markdown body, source references, worker-supplied article date and coverage span, server publication time, and optional deletion time. Do not cascade reporter removal into articles. |
| Worker check-in | Worker identity, server receipt time, Pacific date, and request ID. An empty work response still records a check-in. |
| Operational incident | Stable incident key, type, affected reporter/run/worker when known, first/last observation, resolution time, and notification delivery state. Retain enough information to explain missing results and invalid submissions. |

The pause flag is independent of retirement. A completed contractor and a
manually removed reporter both leave the active roster, but their completion
and removal reasons remain distinguishable. An article's recoverable deletion
does not delete its run or alter the recorded research outcome.

Use numbered database migrations. Enable and enforce foreign-key constraints;
reporter/run references use restrictive deletion behavior. Reporter removal
updates lifecycle fields rather than physically deleting those records.
Keep writes short and do not hold a database transaction across network calls.
Connection settings, migration commands, and schema versioning still need
their final implementation specification.

## Article payload

Proposed worker-supplied article shape:

```json
{
  "title": "Five ideas for the upcoming weekend",
  "summary": "A concise overview of the strongest options.",
  "article_date": "2026-09-24",
  "coverage_start": "2026-09-26",
  "coverage_end": "2026-09-27",
  "body_markdown": "## First option\n\nSee the [official event page](https://example.com/event) for details.\n\n![A hands-on workshop](https://example.com/workshop.jpg)",
  "sources": [
    {
      "title": "Official event page",
      "url": "https://example.com/event"
    }
  ]
}
```

The server assigns article IDs, reporter attribution, run association, and
publication timestamps from the authenticated submission and stored run. The
worker cannot change attribution by placing another reporter ID in an article.
Multiple articles can be submitted in a single successful run result.
The article date and coverage span come from the worker. They need not match
the reporting day or the server's publication date. The
[date contract](database-schema.md#4-articles) uses inclusive calendar dates;
the server validates their format and ordering without inferring a span.

Proposed validation and rendering rules:

- Require nonempty title, summary, and body strings. Title and summary are
  plain text; the article body is Markdown source.
- Support paragraphs, headings, emphasis, ordered and unordered lists, block
  quotes, code blocks, tables, ordinary inline links, and inline images. A
  roundup's entries remain part of one body, not child article records.
- Render normal source links within the body near the statements they support.
  Keep the source list as separate structured metadata for display and future
  UI changes. Do not require readers to understand a custom citation syntax.
- Source objects contain a title and an absolute HTTP or HTTPS URL. The
  exact rule for requiring sources, and whether all inline links must also
  appear in the source list, remain editorial decisions to resolve.
- Disable raw HTML and executable embeds. Render user-supplied text as text,
  and allow only safe link destinations. No client-provided rendered HTML
  becomes the stored source of truth.
- Do not fetch link destinations during validation or page rendering. Source
  research belongs to the worker; schema validation cannot establish that
  a claim is true or that its source supports it.
- Define explicit request and field size limits before exposing the API.
  Markdown parser selection remains open. Inline images are accepted; their
  hosting and validation contract is described below.

Serve deleted articles as unavailable on public pages and through worker
archive retrieval. Restoring an article makes the same record and URL visible
again. Do not regenerate its contents or change its publication time.

### Inline images

The [accepted article format](product-design.md#structured-article-storage)
includes inline images. Use ordinary Markdown image syntax with alt text.
Engineering recommendation: render images within the article's content width,
preserve their proportions, and provide useful alt text. Captions and credits
can be ordinary Markdown text beside the image; this does not require splitting
an article into structured content blocks.

Under the accepted storage choice, the worker includes external image URLs
in the Markdown it submits. The reader's browser loads the images directly
from those hosts. News has no image-upload endpoint, image-file store, image
proxy, or server-side image cache. Image selection belongs to the later worker
phase; server validation and rendering must not fetch image URLs.

Proposed rendering details: require absolute HTTPS image URLs, preserve useful
alt text, and size images to fit the article layout. A missing external image
must not prevent the surrounding article from being read. Allow image syntax
through the Markdown renderer while continuing to reject raw HTML and unsafe
URL schemes.

Deleting or restoring an article hides or restores its Markdown references;
it does not modify the image at its external host. Backups contain the article
text and URLs, with no separate image archive. Caption and credit conventions
can be refined with the reporting worker without adding an upload protocol.

## Browser routes

Proposed route layout:

| Route | Behavior |
| --- | --- |
| `GET /` | Public newest-first feed with title, summary, reporter name, date, and article link. Accept a reporter filter and pagination. |
| `GET /articles/{article_id}` | Public full article rendered from Markdown, with attribution, publication date, and sources. |
| `GET /newsroom` | Owner-only active roster, schedules, pause states, latest outcomes, and worker status. |
| `GET /newsroom/reporters/{reporter_id}` | Owner-only reporter settings, article history, and run history. |
| `POST /newsroom/reporters/...` | Owner-only create, edit, pause, resume, and remove actions. No manual-run action. |
| `GET /newsroom/trash` | Owner-only deleted articles and restore controls. |
| `POST /newsroom/articles/{article_id}/delete` | Recoverably remove one article. |
| `POST /newsroom/articles/{article_id}/restore` | Restore that same article record. |

Trash shows each article's permanent-removal deadline under the accepted
[30-day retention rule](product-design.md#independent-article-lifecycle).
Restoration is available only before that deadline. Afterward, periodic server
maintenance removes the article and its derived search content. There is no
separate permanent-delete button in the proposed v1 route set.

Protect owner mutations against cross-site requests and require owner
authorization on every management operation, not just on the newsroom home
page. Worker credentials do not authorize these routes. The
[access design](implementation-design.md#access-boundary) selects Cloudflare
Access with separate owner and worker policies. Exact credential and origin
validation configuration remain implementation work.

Pagination must use a stable order, including an ID as a tie-breaker for equal
publication timestamps. Public pages can show concise missing-report status;
reporter prompts, detailed errors, credentials, and operational logs stay in
the protected newsroom. Exact visual design and status wording remain open.

## Worker API

Proposed namespace: `/api/v1/worker`. Every operation requires the worker's
credential, including article search and history retrieval. The server obtains
worker identity from authentication rather than trusting a body field.
Use the dedicated Cloudflare Access service token selected in the
[access design](implementation-design.md#access-boundary), with reporting
permissions enforced by News. Its logical worker identity remains stable
when credentials rotate.

| Method and route | Purpose |
| --- | --- |
| `POST /check-ins` | Record the daily work fetch and return currently relevant runs, expected dates, and reporter pause states. Accept a client request ID to make retries safe. An empty list is valid. |
| `POST /runs/{run_id}/claim` | Atomically claim an eligible assignment immediately before starting it. Return the attempt ID, ownership token, expiry, and current prompt/configuration snapshot. |
| `POST /runs/{run_id}/renew` | Renew ownership of the current attempt while work is underway. This is separate from the once-daily discovery cadence. |
| `GET /reporters/{reporter_id}/runs` | Retrieve paginated run history with factual timestamps and explicit outcomes. No calculated coverage window. |
| `POST /runs/{run_id}/result` | Submit articles, a successful empty result, a pause acknowledgment, or an explicit failure. |
| `GET /articles/search` | Search retained article metadata and text with bounded pagination, reporter filters, and optional filters on worker-supplied coverage dates. Exclude deleted articles. No AI search or embeddings on the server. |
| `GET /articles/{article_id}` | Retrieve one retained article for research context. |

This contract permits several API requests during a reporting session. It
does not require the worker to watch for new work throughout the day.
Listing a run does not claim it or establish that research started.
The separate start notification is accepted under the
[start and crash-recovery rules](reporting-worker.md#starting-work-and-recovering-after-a-crash).
The proposed claim endpoint records that notification before local research
begins; it does not create an article.

At claim time, read the current reporter configuration and save the snapshot
used for that attempt. An edit after the claim affects later work, leaving
the active attempt and its recorded instructions unchanged. At most one
research attempt per reporter should run at a time in v1; this prevents
concurrent duplicate research and keeps reporting history ordered.

Paused work needs acknowledgment rather than research. The claim/result
contract must support a pause acknowledgment without pretending research
started. A proposed approach is for the claim operation to return an
acknowledgment-only attempt when the current pause flag is set. It can accept
`skipped_paused`, not newly researched articles. An active attempt claimed
before a pause keeps its original ability to submit completed work.

Apply the accepted [resume behavior](product-design.md#pausing-reporters).
Keep acknowledged recurring occurrences skipped and follow the normal schedule;
today's still-pending occurrence can proceed if the reporter resumes before
the worker starts it. Reoffer a resumed contractor's unfinished assignment
using its original run ID and due date. A new research attempt can follow its
stored pause acknowledgment without modifying the earlier receipt.

Apply the accepted [contractor recovery rule](product-design.md#recurring-reporters-and-one-time-contractors):
when the owner saves changed instructions for an exhausted contractor, reopen
its same assignment with a fresh bounded retry allowance. Discovery can return
it at the next worker check. Preserve the due date and earlier attempts, and
continue to enforce pause and deletion. The worker cannot reset its own retry
allowance through claim or result requests.

The exact ownership-token recovery mechanism, lease durations, retry delays,
and behavior when configuration changes between listing and claiming remain
to be specified. Do not implement these endpoints as independently changing
run state without a shared transaction layer.

Support the accepted recovery sequence: retry delivery of locally saved
completed results first, then replace unfinished attempts and restart research
within the retry limit. Retain old attempts. A replaced attempt cannot submit
a new result, but an identical retry of an accepted submission returns its
stored receipt. The server does not need to store partial articles or model
conversations to support this sequence.

## Result submission

Proposed result envelope for a published report:

```json
{
  "submission_id": "worker-generated-stable-id",
  "attempt_id": "server-issued-attempt-id",
  "ownership_token": "attempt-credential",
  "outcome": "published",
  "articles": [
    {
      "title": "A report title",
      "summary": "A short plain-text summary.",
      "article_date": "2026-09-25",
      "coverage_start": "2026-09-01",
      "coverage_end": "2026-09-24",
      "body_markdown": "The report, with [source links](https://example.com/source).",
      "sources": [{"title": "Source", "url": "https://example.com/source"}]
    }
  ]
}
```

Do not log credentials or complete request bodies as routine diagnostics.

| Outcome | Payload rule | Effect |
| --- | --- | --- |
| `published` | One or more valid articles. | Publish all articles and finish the run successfully. |
| `nothing_to_publish` | No articles; include a concise reason. | Finish successfully without creating an article or inferring coverage metadata. |
| `skipped_paused` | No articles; identify the acknowledged pause. | Satisfy the expected signal without claiming successful research or completing a contractor. |
| `failed` | No articles; structured error code, readable explanation, and retry classification. | Record the failed attempt and apply bounded retry rules. |

Validate the complete result before publishing any article. If any article is
invalid, reject the result without partial publication. Research success,
article insertion, the stored receipt, and contractor completion must commit
in one database transaction. Send notification email outside that transaction.

For a valid published result, return a receipt containing the run ID,
submission ID, accepted outcome, and generated article IDs. Store a canonical
payload digest with the receipt:

- Retrying the same submission and payload returns the original receipt.
  It must not publish duplicates, trigger another alert, or undo later manual
  article deletion or recreate content purged after its 30-day Trash period.
- Reusing a submission ID with different content is a conflict.
- A new payload for an already completed run cannot replace its result or add
  articles. Published articles have no correction/editing workflow in v1.
- Enforce the accepted [post-deletion rule](product-design.md#reporter-removal-and-stable-identity):
  accept valid work already underway before deletion, reject and alert on
  new reporting started afterward, and distinguish harmless delivery retries.

Proposed responses: `200` with a receipt for accepted submissions and identical
retries; `401` for missing/invalid authentication; `403` for insufficient
permissions; `404` for unavailable records; `409` for state or idempotency
conflicts; and `422` for an invalid result shape. Return a stable error code
and explanation with each API error. Only authenticated worker faults should
generate worker incident alerts; arbitrary unauthenticated requests must not
be able to flood the owner's email.

## Schedules and worker-supplied coverage

The server stores day-based schedules, not worker execution hours. Each due
date has one logical occurrence. Midnight boundaries use `America/Los_Angeles`
and the accepted [overdue rule](reporting-worker.md#overdue-window-for-day-based-schedules).
Maintenance makes missing work visible even if the worker sends nothing.

Apply the accepted [schedule activation rule](product-design.md#schedules-by-day):
new schedules and schedule changes start tomorrow in Pacific Time. Preserve
today's assignments under the previous schedule. Preview the first expected
date before the owner saves, and validate a new one-time date as tomorrow or
later. This affects scheduled occurrences, not when the worker chooses to
execute or which coverage span it reports.

For monthly schedules, apply the accepted
[month-end rule](product-design.md#schedules-by-day): use the last day when
the selected day does not exist, while retaining the selected day for later
months. Preview and actual occurrence generation must use the same rule.

For recurring catch-up, retain missed occurrences and identify one current
catch-up run. Link superseded missed occurrences to it rather than rewriting
them as successful runs. The prompt and worker determine the research span.
The server supplies ordinary records when requested, including each article's
worker-supplied coverage dates. It does not choose a lookback interval, a
first-run fallback, or upper and lower research boundaries. New reporters
simply have no past reporting history.

The worker submits each article's coverage metadata alongside its content.
The server stores it, returns it, and can filter for overlapping spans using
those explicit dates. Publication time, expected reporting day, and successful
empty outcomes do not establish coverage. There is no server-maintained
last-covered field.

Keep a missed one-time assignment available under the accepted
[contractor policy](product-design.md#recurring-reporters-and-one-time-contractors).
Return its original due date and instructions; do not expire it automatically
or create a replacement recurring catch-up run. The worker can complete it
with articles or a successful empty result explaining that it is no longer
useful. Failure remains subject to bounded retries.

Apply the accepted [category rule](product-design.md#recurring-reporters-and-one-time-contractors):
reject edits that convert an existing reporter between recurring and one-time.
Recurring cadence changes remain supported. Creating another reporter does
not reassign the original reporter's articles or pending work.

## Verification and remaining work

Use the [server acceptance cases](implementation-design.md#proposed-server-acceptance-approach)
with a deterministic API client and representative article fixtures. Exercise
real persistence, rendering, authorization boundaries, and state transitions.
No real model is needed to establish those outcomes. Add focused failing tests
before implementing each behavior, as required by the project workflow.

This draft makes the article and submission interfaces concrete, but it does
not complete the deployment design. Authentication provider setup, supported
Python/tool versions, Markdown renderer, schema limits, search implementation,
exact retry/lease rules, configuration of the selected
[email delivery](implementation-design.md#email-delivery),
backup/restore, and rollout commands remain to be specified. Model integration
and research quality evaluation remain in the later worker phase.
