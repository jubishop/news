---
status: draft
---

# Product design

This document develops the [concept](concept.md) into requirements for the
first useful version of News. Accepted decisions are recorded below. Open
questions remain proposals, not approved requirements. No application is
implemented yet.

The [implementation design](implementation-design.md) records the deployment
context and develops the technical approach. The
[reporting examples](reporting-examples.md) define concrete assignments to
evaluate.

## Accepted decisions

### Audience and ownership

Revised on September 25, 2026: the reading site at `news.jubishop.com` is
public. Visitors can read published articles without signing in. The API
must require authentication. The project still has one owner who directs
the reporters; separate newsrooms for multiple owners remain outside v1.

This supersedes the September 24, 2026 decision to make readership private.
The owner does not see a need to restrict the reading site. The tradeoff is
that published articles are available to anyone; a browser login is no longer
a condition for reading them.

Accepted on September 25, 2026: the newsroom is owner-only. Require owner
authentication for its pages and management actions, including access to
reporter instructions, settings, and detailed run history. The owner agreed
that the newsroom should be restricted; no further reason was stated. This
keeps editorial control with the owner while articles remain publicly readable.

The [access design](implementation-design.md#access-boundary) selects Cloudflare
Access for owner sign-in and separate worker credentials. Exact credential
and deployment configuration remain implementation work. Public reading does
not imply anonymous API access.

### Automatic publication

Accepted on September 24, 2026: reporters publish automatically. Articles do
not wait for the owner's approval. The first version has no manual workflow
to edit or correct published articles.

The owner wants to read the output without reviewing or changing it after
publication. Direction happens through reporter configuration. The tradeoff
is that the owner does not check each article before it appears. Automated
publication requirements and handling of reporting errors remain open.

The [prompt-editing workflow](#editorial-guidance-through-prompt-edits) lets
the owner direct future reporting after reviewing prior output. Manual
[article deletion](#independent-article-lifecycle) is supported separately.

### Newsroom controls

Accepted on September 24, 2026: a newsroom page lists the owner's reporters
and exposes each reporter's prompt (its beat) and schedule.
The owner can change these settings, add reporters, and delete reporters.

The purpose is to inspect and direct the reporting from one place. Model
selection is not a newsroom control; all reporters use the shared model
defined below.

Accepted on September 25, 2026: omit a "Request a run" or "Run now" action
from the newsroom. The owner would start any extra run directly on the
worker's machine. This rejects the proposed manual-run UI, not scheduled
reporter creation or editing.

The owner's reason is that the worker
[checks for work once a day](reporting-worker.md#daily-work-discovery), so a
newsroom request would not cause immediate execution. The tradeoff is that
extra runs require access to the worker's machine. The specific worker-side
command and its API interaction remain part of the later worker design.

### Pausing reporters

Accepted on September 25, 2026: include Pause/Resume in the v1 newsroom.
A paused reporter remains in the newsroom with its prompt, schedule, and
article history. Paused days require no new research, but the worker still
[acknowledges the pause](reporting-worker.md#pause-acknowledgments-and-worker-contact).
The owner can resume the reporter without recreating it; pausing is distinct
from deleting a reporter.

The owner accepted the recommendation; no further reason was stated. It
supports temporary breaks while retaining the reporter's configuration and
identity. The tradeoff is an additional reporter state that scheduling and
monitoring must respect.

Clarified on September 25, 2026: pausing sets a flag that the worker must
respect before starting further work. It does not cancel work already underway.
If the worker has a finished report when it notices the flag, it submits that
report rather than discarding it. The server accepts and automatically
publishes an otherwise valid result from work already underway even while the
reporter is paused. Setting the flag alone must not invalidate that run.

The owner's reason is to preserve completed reporting. The tradeoff is that
an article can still appear after its reporter is paused. There is no remote
cancellation or continuous pause-check requirement. Work not started is skipped
while paused, with an explicit acknowledgment rather than silence.

Further clarified on September 25, 2026: pausing must not hide a worker that
has stopped communicating. This supersedes the earlier assumption that paused
dates require no signal or missing-result monitoring. The
[worker monitoring rule](reporting-worker.md#pause-acknowledgments-and-worker-contact)
distinguishes an acknowledged pause from a missing worker signal.

Accepted on September 25, 2026: resuming a recurring reporter returns it to its
normal schedule. Occurrences already acknowledged as paused remain skipped;
resuming does not generate catch-up work for those occurrences. A Thursday
reporter resumed on Friday waits until the next Thursday. If today's scheduled
run is still pending when the reporter resumes, the worker may perform it
when it checks.

An unfinished contractor becomes available at the next worker check after
resumption. Retain its original dates and pause acknowledgments, then combine
unfinished due dates under the [contractor catch-up rule](contractor-schedules.md).

The owner accepted this recommendation; no further reason was stated. It
preserves recurring schedules while allowing a paused contractor to finish
its unfinished assignments. The tradeoff is that recurring reporting may wait until
the next scheduled day. The prompt and worker still determine the article's
coverage span, including how to treat the gap during a pause.

### Reading experience

Accepted on September 24, 2026: the first reading interface is a newest-first
article feed with a reporter filter. Named sections are deferred beyond v1.

The user accepted this recommendation; their reason was not stated. It gives
the owner a simple way to read and browse while the UI develops independently
of stored articles. The tradeoff is that articles from several reporters are
not grouped into named topic sections in this version.

The reading site also shows
[missing or late reporting](reporting-worker.md#timeliness-and-completion).

Accepted on September 25, 2026: the feed shows each article's title, short
summary, reporter name, and date, with a link to a separate full article page.
The owner agreed to the recommended layout; no further reason was stated.
This keeps long reports from overwhelming the feed. The tradeoff is an
additional navigation step to read an article in full.

### Editorial guidance through prompt edits

Accepted on September 24, 2026: the reporter's prompt contains its editorial
instructions. The newsroom provides access to the reporter's past articles
and direct editing of its prompt, schedule, and supported settings.
There is no dedicated article feedback feature in v1.

The owner can use Codex to help rewrite a prompt after reviewing an article,
then save the revised prompt through the newsroom for future runs. This initial
workflow does not require Codex to connect directly to the production database.
Automatic prompt rewriting and a separate store of active feedback are outside
v1. Prompt changes do not modify previously published articles.

The user accepted this simplification after suggesting that Codex could help
with prompt revision. It gives each reporter one clear set of editorial
instructions and avoids accumulating conflicting feedback notes. The tradeoff
is a manual step to transfer the revised prompt into News. Automatic coverage
memory and archive search remain part of reporting; they serve a different
purpose from editorial guidance.

Retain the exact prompt used for each run so later edits do not obscure the
instructions that produced an older article. Prompt snapshot details remain
open. The shared-model decision below removes the earlier model-recording
requirement.

This replaces the earlier decision on September 24, 2026 to add a dedicated
article feedback workflow. The ability to review prior articles and change
reporter settings remains.

### One shared reporting model

Accepted on September 24, 2026: all reporters use the same model. Model choice
is not configurable per reporter or through the newsroom, and articles do not
have a model field. The model is a shared implementation choice.

The owner stated that they will use the same model for every reporter; no
further reason was given. This simplifies reporter settings, article metadata,
and model integration. The tradeoff is that individual beats cannot select
different models.

This supersedes the earlier September 24, 2026 decisions to support
per-reporter model selection, multiple providers at launch, and saving a model
alongside each run's prompt. The [worker design](reporting-worker.md#model-engine)
records the selected vanilla Codex CLI with GPT-6.1 Sol, high reasoning, and built-in web
research, which supersedes the earlier Qwen/Pi choice.

### Recurring reporters and one-time contractors

Accepted on September 24, 2026: most reporters run on a repeating schedule;
contractors support finite assignments and leave the active roster after
successful completion. On September 28, the owner extended contractors to
any number of specific dates, keeping one Contractor option. A single date
remains the simplest case.

The [contractor date rules](contractor-schedules.md) record the accepted date
editing, catch-up, completion, pause, and retry decisions. They supersede the
original single-date restriction and retirement after the first successful
result. Articles and run history remain after retirement.

Accepted on September 25, 2026: a reporter's category is fixed after creation.
Recurring reporters can change between daily, weekly, and monthly schedules.
Contractors remain finite date lists. To change category, create a new
reporter; articles retain their original attribution. The owner accepted the
recommendation without a further stated reason. This avoids changing
completion rules while work is underway, at the cost of creating a new
reporter for a different category.

### Schedules by day

Accepted on September 25, 2026: schedule reporting by day, with daily, weekly
on selected days, monthly, and contractor assignment dates. The newsroom does not ask
for a clock time. The worker chooses when to execute within a reporting day;
the server does not need that planned execution time. Interpret reporting
dates in Pacific Time.

The owner wants execution timing to remain a worker responsibility. The
tradeoff is that the server can assess missing reporting against an expected
day, but cannot identify lateness relative to the worker's preferred hour.
The earlier one-hour deadline from a scheduled time is superseded; the
[replacement overdue window](reporting-worker.md#overdue-window-for-day-based-schedules)
allows the full reporting day.

Accepted on September 25, 2026: new reporters and schedule changes take effect
starting tomorrow in Pacific Time. The first expected run uses the next
matching scheduled date after today. Schedule edits preserve today's existing
assignments and change future dates. New contractor dates must be scheduled
for tomorrow or later. Show the first expected reporting date in the newsroom
before saving.

The owner accepted this recommendation; no further reason was stated. Because
the worker discovers work once a day, it may already have checked when a new
schedule is saved. Starting tomorrow avoids requiring a result before the
worker has a chance to discover it. The tradeoff is no same-day scheduling
through the newsroom, even when the worker has not yet checked. This rule
applies to schedules; it does not postpone the existing pause, deletion, or
prompt-edit behavior.

Accepted on September 25, 2026: when a monthly schedule's selected day does
not exist in a month, use that month's last day. Retain the selected day for
later months. For example, a schedule for the 31st uses April 30 and February
28 or 29, then returns to the 31st in months that contain it.

The owner accepted this recommendation; no further reason was stated. It
preserves reporting once each month instead of skipping shorter months. The
tradeoff is that the calendar day can vary. This rule determines reporting
dates only, never the worker-supplied article coverage span.

### Assignment-controlled output

Accepted on September 24, 2026: the assignment determines whether a reporting
run produces a combined report or separate articles and what form the content
takes. There is no fixed one-article-per-run rule.

The user selected assignment-controlled output; their reason was not stated.
It supports both recurring roundups and focused one-time research. The
tradeoff is that the reporting and storage interfaces must support multiple
articles from one run. Default behavior for an unspecified format remains open.

### Best-effort assignments

Accepted on September 26, 2026: all assignments are best effort. Apply this
as a default even when the reporter's prompt does not state it explicitly.
A request for five worthwhile items can produce three supported items with
a brief explanation when that is the useful result. Do not fail a run solely
because it cannot meet a requested count or supply every requested detail.

The owner stated that this should be implied by prompts. The tradeoff is
variable completeness in exchange for useful reporting without filler.
Best effort does not permit invented facts or concealment of material gaps.
Keep research failures distinct from successful partial reporting and the
existing successful "nothing to publish" outcome.

### Runs with nothing to publish

Accepted on September 24, 2026: a run may publish no articles when it finds no
worthwhile material. The newsroom shows this as a successful "nothing to
publish" result, distinct from a failed run.

The user accepted this recommendation; their reason was not stated. It avoids
filler articles while confirming that the reporter completed its research.
The tradeoff is that successful reporting does not always add something to
the reading feed, so run outcomes must be visible independently of articles.

A research failure must not be presented as a successful empty result. Record
a successful run with no articles as successful reporting in the run history,
separately from the last run that published an article. The server does not
infer a covered date range from that outcome under the
[coverage rule](#reporting-memory-and-coverage-window).

### Failed runs and notifications

Accepted on September 24, 2026: failed reporting runs receive a small, bounded
number of automatic retries. If those attempts fail, send the owner one email
alert and show the failure in the newsroom. A successful "nothing to publish"
result does not trigger a failure alert.

The user accepted this recommendation; their reason was not stated. Email
helps the owner notice broken reporting without checking the newsroom
regularly. The tradeoff is an email integration and delivery state in addition
to the reporting workflow. An unresolved reporting failure remains visible
even if its alert cannot be delivered.

Retry count, retryable error types, delay between attempts, email delivery
retries, and the behavior of later scheduled runs remain implementation
decisions. Retries must not generate duplicate published articles or multiple
logical failure alerts for the same run. The
[email delivery design](implementation-design.md#email-delivery) selects Resend
with separate News credentials and a deployment-configured recipient.
The server also detects [missing run outcomes](reporting-worker.md#timeliness-and-completion)
independently of worker-reported errors.
Apply the accepted [alert grouping policy](reporting-worker.md#alert-grouping)
when a worker outage affects several reporters. Keep their individual missing
results visible while sending one outage email without daily reminders.

Accepted on October 1, 2026 (td-07237e): add immediate, local macOS notices for
final reporter failures and worker operational errors caught by the Mac worker.
Keep the existing server email alerts. The local worker does not poll for server
incidents, send desktop notices for server-only alerts, retry notifications in
the background, or replay notices for old result receipts. The owner's reason
for this scope was not stated. This is an accepted worker design; it does not
change the server alert policy above.

### Structured article storage

Accepted on September 24, 2026: stories are stored as structured records in a
database, independently of the UI. Generated HTML pages are not the source of
truth for article content. The UI renders the stored articles.

The owner's reason is to change and iterate on the UI without tying the
reporting to a particular page layout. This requires a defined article data
format and database persistence. SQLite is the
[selected database](implementation-design.md#accepted-core-stack).

Accepted on September 25, 2026: each article has a title, summary, one Markdown
body, and separate source references, with reporter attribution and dates.
A roundup such as five weekend activities is one article body. Its individual
entries do not need separate structured records in v1. An assignment can still
produce several articles, each with its own body.

Reaffirmed on September 25, 2026: article bodies are Markdown and must support
inline links. Store Markdown source and render it for the full article page.
The [server contract](server-contract.md#article-payload) develops the concrete
fields and rendering rules within this accepted format.

Accepted on September 25, 2026: support inline images in Markdown article
bodies in v1. The owner explicitly requested images; no further reason was
stated. This extends the article format beyond the proposed text-and-links
starting point.

Also accepted on September 25, 2026: images load directly from external URLs
in the Markdown body. News stores those references, not image files. The owner
does not want the server to manage image storage or image-upload API operations.
The tradeoff is that image availability depends on the external host. This
rejects the proposal to upload and retain copies on the VPS. The
[image delivery contract](server-contract.md#inline-images) follows that choice.

The owner explicitly preferred a single body and agreed to the recommended
format; no further reason was stated. This supports headings, lists, tables,
and links without requiring a separate schema for every assignment type. The
tradeoff is that individual roundup entries cannot be queried or rearranged as
structured items without interpreting or changing the body. Exact source
fields, validation limits, rendering rules, and caching remain to be specified.

### Independent article lifecycle

Accepted on September 24, 2026: articles remain available after their reporter
is deleted or their one-time contractor is gone. The owner can manually delete
an individual article. There must be no deletion cascade from a writer to its
articles: deleting the writer must not automatically delete any of its output.

The owner's reason is to keep published stories independently of the reporters
that produced them, while retaining direct control over article deletion.
The data model must preserve article content, its original stable reporter ID,
and enough attribution to display it independently of the active newsroom
roster. This adds a separate article lifecycle rather than using reporter
deletion to clean up content.

Also accepted on September 24, 2026: manual article deletion is recoverable.
Deleted articles are removed from reading views and future reporting context,
with a restore option in the newsroom.

The user accepted recoverable deletion; their reason was not stated. It
protects against accidental deletion while keeping unwanted content out of
normal use. The tradeoff is retaining deleted content for restoration.

Accepted on September 25, 2026: permanently remove deleted articles after
30 days in Trash. The owner selected this over indefinite retention; no further
reason was stated. Offer restoration before the deadline, and show that deadline
in the newsroom. Purging removes the article body, title, summary, source
metadata, and any derived search content from the live database. Retain the
minimal run and submission receipt needed to prevent a worker retry from
recreating it. Backup copies expire through the normal
[backup retention policy](backups.md); external image hosts are unaffected.
Retired reporter and run-history retention remains an engineering detail.

### Reporter removal and stable identity

Accepted on September 24, 2026: deleting a reporter ends its active role.
Do not build reassignment, replacement, inherited coverage, or reporter-merging
features in v1. Articles retain their original reporter ID after reporter
removal, as required by the independent article lifecycle.

The owner rejected the handoff concept as unnecessarily complex for now.
Keeping article history associated with stable reporter IDs leaves room to
add a handoff feature later, if it becomes useful. The tradeoff is that a new
reporter has its own identity and reporting history rather than taking over
another reporter's role through a dedicated workflow.

This supersedes the earlier September 24, 2026 decisions about reporter
succession, combined coverage, and copying predecessor settings. The existing
ability to search the full article archive remains; it does not transfer
articles or their authorship between reporters.

Clarified on September 25, 2026: if work is already incoming when the owner
deletes a reporter, accept its otherwise valid result and publish its articles.
Deletion removes the reporter from the active newsroom and stops future
assignments; it does not discard work already underway or invalidate its run.
Incoming articles retain the reporter's original identity, and accepting them
does not restore the reporter to the active roster.

The owner explicitly chose to accept incoming work; no further reason was
stated. The tradeoff is that new articles can appear after their reporter has
been removed. Retain enough reporter and run information to accept and attribute
that work without recreating an active reporter.

Further clarified on September 25, 2026: accepting incoming work is a limited
allowance for a run that began before deletion. Ongoing new reports for a
deleted reporter are an error, and the server must alert the owner when they
arrive. The owner expects the daily work fetch to stop the worker from
continuing that reporter beyond work already in progress around deletion.

The reason is to detect a worker using stale assignments or otherwise behaving
incorrectly. The tradeoff is that the server must distinguish an expected
final submission from new work and harmless delivery retries. Do not interpret
this allowance as indefinite permission to publish for a deleted reporter.

Accepted on September 25, 2026: reject unexpected new reporting for a deleted
reporter and alert the owner. An otherwise valid result from work started
before deletion is still accepted. An identical retry of that submission is
acknowledged without creating duplicate articles or false alerts.

The owner accepted rejection in addition to notification; no further reason
was stated. This prevents unintended publication while making the faulty
worker behavior visible. The tradeoff is that the rejected content does not
enter the reading feed. Detailed run validation and expiration rules remain
to be specified.

### Research sources

Accepted on September 24, 2026: reporters use open web research by default.
An assignment can identify preferred sources or restrict research to selected
sources. Both open research and source-restricted assignments are supported.

The user accepted this default; their reason was not stated. It allows broad
discovery while preserving control for assignments that need specific sources.
Preferred sources guide research without excluding other sources. A strict
source restriction limits the sources the reporter may use. The exact control
format, search and retrieval tools, and enforcement remain open.

### Reporting memory and coverage window

Accepted on September 24, 2026: recurring reporters receive a summary of their
recent articles and can search the full article database. Past reporting
provides context for the worker.

The user agreed to this approach; their reason was not stated. It helps avoid
repeats, supports follow-up reporting, and lets a reporter find related work
by another reporter. The tradeoff is that reporting requires archive retrieval
and a bounded selection of prior coverage. Summary size and archive search
remain implementation details to specify.

Clarified on September 25, 2026: the prompt specifies the coverage span, and
the worker's AI interprets it. The server stores and presents reports and
checks whether expected outcomes arrived by the agreed deadlines. It makes
no inference about what period an article covers. Do not derive a lookback
from the schedule, supply a fixed first-run fallback, or compute lower and
upper research dates on the server.

Also accepted on September 25, 2026: the worker supplies each article's
coverage span with its other article metadata. The server retains it so
reporters can use it when fetching past articles. This is worker-authored
metadata, never a server inference. The server may validate its shape and
use supplied dates in ordinary database filters; it must not invent missing
coverage or replace the worker's span with a calculated one.

The owner's reason is that the prompt and worker AI should choose the span,
while retaining it makes article history more useful. The tradeoff is that
the server can validate metadata but cannot establish whether the article
actually covers that period.

Clarified on September 30, 2026: keep coverage windows and research cutoff
timestamps out of article titles, summaries, and bodies. The owner rejected
the repeated "Coverage: ... through ..." opening in that day's stories. Use
the existing coverage metadata and page dateline for coverage dates. Start
the body with the story, and retain dates that explain the news or define an
event or recommendation period.

This supersedes earlier proposals for a server-maintained last-covered
timestamp, automatically supplied research-date ranges, and a first-run
lookback based on cadence. Ordinary article and run timestamps remain factual
record metadata. They are separate from the worker-supplied coverage span.

The earlier examples remain assignment requirements. A research prompt asking
for developments "since your last report" should let the worker account for
missed weeks. The [weekly activity assignment](reporting-examples.md#weekly-family-activity-shortlist)
targets an upcoming weekend and uses prior reporting for recommendation
rotation. The [recovery policy](reporting-worker.md#missed-recurring-runs-and-catch-up)
combines missed recurring work into one run; it does not choose that run's
research span. Successful empty results remain distinct in run history, but
the server does not fabricate an article or a coverage span for them.

### Hosting constraint

Accepted on September 24, 2026: News will run at `news.jubishop.com` on the
owner's existing Hetzner VPS, alongside the other services for `jubishop.com`.
The VPS has limited compute and memory. The design must fit this shared host.
The [worker location decision](reporting-worker.md#worker-location)
allows reporting to run on a separate machine; the website and database stay
on the VPS.

This is the owner's stated deployment plan. The existing infrastructure in
`~/projects/vps-infra` and deployed projects under `~/projects` are the local
references for implementation choices. Sharing the host avoids a separate
hosting platform but requires controlling News resource use so it can coexist
with the other applications. The
[core stack is selected](implementation-design.md#accepted-core-stack);
resource limits remain open.

Clarified on September 24, 2026: current VPS capacity is a starting constraint,
not a permanent ceiling. The owner can expand it when needed and can move
Screenr, the application they expect may need public-traffic scaling, to a
different host. The design should not sacrifice useful capabilities merely
to preserve the current server size. This is a planning option, not a decision
to resize the server or move an application now.

## Open design questions

The main server product choices are now recorded, including 30-day Trash and
the newsroom restore action. No further owner decision is currently required
to begin server implementation.

Engineering work before and during server implementation includes completing
field limits, Markdown rendering, archive search, retry and claim timing,
retained operational history, and deployment configuration. The
[server contract](server-contract.md),
[acceptance cases](implementation-design.md#proposed-server-acceptance-approach),
and [backup policy](backups.md) define the current requirements. These details
do not reopen accepted scheduling, authentication, article-format, or coverage
decisions.

The later worker phase still needs research tools, source-quality rules,
editorial defaults where prompts are silent, and reporting-quality evaluation.
Those choices must not block the server-first sequence.
