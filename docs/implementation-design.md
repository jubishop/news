---
status: draft
---

# Implementation design

This document develops the technical approach for the accepted
[product requirements](product-design.md). Python, Flask, and SQLite are
selected. Accepted choices, deployment observations, and recommendations are
identified separately. The application is not implemented yet.

The proposed [server contract](server-contract.md) defines records, article
payloads, browser routes, and worker API operations for the first phase.
The [database schema](database-schema.md) is the accepted six-table baseline;
its remaining behavioral questions do not reopen that structure.

## Implementation sequence

Accepted on September 25, 2026: implement and deploy the newsroom server on
the VPS first. Bring that server to a v1 the owner is happy with before
separately implementing the reporting worker on one of the owner's local
machines. The specific local host and model engine remain undecided.

The owner requested this sequence; no further reason was stated. It allows
the reading experience, reporter management, storage, and API to be evaluated
before adding real AI reporting. The tradeoff is that server acceptance cannot
establish research quality or prove the eventual worker integration.

The first phase includes the server side of the worker API and its job
lifecycle. Define that interface now so the later worker can use it. Model
integration, research tools, and local worker deployment belong to the second
phase and must not become prerequisites for completing the server.

### Proposed server acceptance approach

These are engineering recommendations for making server v1 reviewable without
a production worker:

- Verify the [backup policy](backups.md) with an isolated database restore,
  paginated storage measurements, threshold crossing and recovery, and failed
  notification delivery. Check that backups continue above the threshold and
  that a failed measurement cannot clear an existing warning.

- Exercise reporter creation, instruction and schedule edits, pause/resume,
  removal, and one-time assignments through the newsroom. Verify that paused
  days require no new research, an explicit pause acknowledgment satisfies the
  expected signal, and the reporter's configuration and history remain available.
- Create and change schedules before and after the daily worker check. Verify
  that the first newly scheduled date is after today, today's existing work
  stays intact, and the newsroom preview matches the saved first due date.
  Reject new one-time dates of today or earlier. Use Pacific calendar days,
  including across daylight-saving changes.
- Verify that recurring reporters can change between daily, weekly, and monthly
  schedules, while edits crossing between recurring and one-time are rejected.
  Creating a new reporter must not reassign another reporter's history.
- Verify monthly schedules for the 29th, 30th, and 31st in shorter months,
  including leap-year February. Preserve the selected day so a 31st schedule
  returns to the 31st after a short month instead of permanently changing it.
- Submit a pause acknowledgment and verify that it records worker contact
  without creating an article or claiming successful research. Withhold the
  expected signal and verify that pausing does not hide the missing communication.
- Resume a recurring reporter after a skipped occurrence and verify that it
  follows its normal schedule without creating catch-up work for that skip.
  Resume before today's pending occurrence is claimed and verify that it can
  run today. Resume a contractor after its due date and pause acknowledgment;
  verify that it can complete the original assignment through a new attempt
  while retaining the acknowledgment and original due date.
- Start a run through the API, pause its reporter through the newsroom, and
  submit its result. Verify that the valid result is accepted and its articles
  appear while the reporter remains paused.
- Repeat with deletion of a reporter whose work has started. Its incoming
  result must publish with original attribution, while the reporter stays
  removed from the active roster and receives no future assignments.
- Verify that ongoing new reporting for a deleted reporter is rejected and
  creates an alert,
  while an identical retry of a previously accepted submission creates neither
  another article nor a false alert.
- Verify that a daily work fetch with an empty assignment list still records
  worker contact, and that contact does not conceal missing individual results.
- Simulate a worker outage spanning several reporting days and reporters.
  Verify one logical outage email, no daily reminders or separate missing-run
  emails for that outage, and continued visibility of all missing work. While
  worker contact is healthy, exhaust one run's retries and verify its own alert.
- Verify that a contractor leaves the active roster after publishing or a
  successful empty result. Failure, lateness, and pause acknowledgments keep
  it visible with its status, and completing it preserves its articles.
- Exhaust a contractor's retry allowance, then save changed instructions in
  the newsroom. Verify that the same assignment becomes eligible for a fresh
  bounded allowance and retains its earlier attempts. Unchanged saves, name
  edits, and repeated daily checks must not replenish that allowance. A paused
  or deleted reporter must still follow its respective eligibility rules.
- Withhold worker contact past a contractor's due day. Verify that the same
  assignment remains available with its original due date when contact resumes.
  Accept a successful empty result explaining that the assignment is no longer
  useful, without adding server-side expiration or usefulness inference.
- Use a small test client and deterministic article fixtures to exercise the
  real API: obtain work and context, submit articles, report nothing to publish,
  and report failure. This client performs no AI work.
- Record a start notification, then simulate the worker disappearing before
  submission. Verify that the server has an attempt but no article. Exercise
  replacement within the retry limit and reject new results from the replaced
  attempt. Simulate losing an acknowledgment after a successful submission;
  replay the saved result and verify that it returns the original receipt
  without duplicate publication. Local result storage belongs to the later
  worker phase; server v1 tests use deterministic saved payloads.
- Verify automatic article availability, feed filtering, historical
  attribution, and recoverable article deletion through the reading UI and
  newsroom. Use varied fixtures, including a five-item roundup and multiple
  articles from one run, to test the stored content format. Include inline
  links and externally loaded images, verifying their rendering at narrow and
  wide page widths. Verify that missing images leave the article readable and
  that the server does not fetch or store image content.
- Restore an article before its 30-day Trash deadline, and reject restoration
  at and after the deadline. Run cleanup and verify removal of its content and
  search entries. Retry the original accepted worker submission after purge;
  it must return its old receipt without recreating any article. Verify that
  restore and purge cannot race into resurrecting expired content.
- Verify the job lifecycle through the public interface, including missed
  results, day-based schedules and overdue detection, retries, duplicate submissions,
  catch-up assignments, and recovery after server restart. Use controlled time in
  automated tests so these checks do not require waiting for real deadlines.
- Store, return, and filter each article's worker-supplied coverage dates.
  Include past and future spans distinct from scheduled and publication dates.
  Verify that the server never supplies missing coverage dates or derives a
  research window from cadence or run outcomes.
- Validate anonymous reading and authenticated API access, worker permissions,
  persistence and restoration, and deployment at `news.jubishop.com`. Under the
  accepted newsroom access rule, verify that anonymous visitors cannot view
  reporter instructions or perform management actions. Keep test data separate
  from the owner's real reporting history.

Automated tests must run real server logic with fakes only at external-system
boundaries, following the [testing workflow](development-workflow.md#test-driven-development).
The deployed server and representative fixtures give the owner a concrete v1
to assess. Worker implementation starts after the owner is satisfied with that
server milestone. Final API schemas and acceptance cases still need to be
completed as part of the server design.

## Existing deployment context

The [hosting decision](product-design.md#hosting-constraint) puts News at
`news.jubishop.com` on the existing shared Hetzner VPS. Current capacity can
grow; it is not a permanent product limit.

Reviewed on September 24, 2026:

- `~/projects/vps-infra` contains the shared host and Cloudflare procedures.
  The documented setup uses Ubuntu, systemd services, Caddy as the web proxy,
  and Cloudflare-proxied DNS. The root domain uses GitHub Pages; the relevant
  application hosting pattern is the VPS subdomains.
- `~/projects/kidsbank/memory/project_deployment.md` documents a Node.js and
  Express application with SQLite and Cloudflare Access.
- `~/projects/trading/docs/DEPLOYMENT.md` documents Python, Flask, gunicorn,
  SQLite, and cron jobs. Its current app instructions and deployment guide
  say it is public. The older shared infrastructure memory still describes
  Cloudflare Access for Trading; do not copy that stale access assumption.
- `~/projects/screenr/docs/application-stack.md` and `docs/deployment.md`
  describe TypeScript, Next.js, PostgreSQL, separate web and worker services,
  resource limits, and release builds outside the VPS. Screenr manages its
  own authentication. Its stack is evidence of the host's deployment options,
  not a requirement to select the same stack for News.

A read-only host check on September 24, 2026 found two logical CPUs, 1,920 MiB
of RAM, no swap, and about 37 GiB of disk capacity. This is deployment context,
not a measurement of News resource use or a capacity guarantee. Recheck the
host and measure representative News workloads before deployment.

## Loose workload estimate

On September 24, 2026, the owner accepted about ten recurring reporters,
mostly weekly with some daily runs, plus occasional contractors as an early
planning estimate. They questioned the need to specify this now. Treat it
only as context for initial job concurrency and cost estimates, not as a
product limit, capacity commitment, or prerequisite for further design.

## Accepted core stack

Accepted on September 24, 2026: use Python, Flask with Jinja templates, and
SQLite, with a separate Python reporting worker. The owner accepted the
recommendation; their reason was not stated. The engineering rationale follows
the reading and newsroom requirements, not an assumed preference from
neighboring projects.

| Component | Responsibility | Reason and tradeoff |
| --- | --- | --- |
| Flask and Jinja | Render the reading feed, article pages, and newsroom forms from database records. | The agreed UI is mainly reading, filtering, and editing settings. Templates support this directly. A richer browser application remains possible but would require additional interface work. |
| SQLite through Python's `sqlite3` | Store reporters, articles, run state, and pending work. | Local structured data and short writes fit the starting application. It needs no separate database server, but concurrent writers must keep transactions short. |
| Separate Python worker | Claim reporting work, call research services, and submit results or errors. | Research continues independently of a browser request and can run on a different host. The application must own durable job state and recovery rules. |
| Existing Caddy and systemd | Route HTTPS traffic and supervise VPS application processes. | Fits the shared host's deployment model. Service settings and resource limits still require validation. Worker supervision depends on its eventual host. |

Article content stays in the database using the
[selected article format](product-design.md#structured-article-storage).
Changing page templates does not regenerate or change the stored reporting.
Keep database access and reporting logic outside page handlers so UI changes
can reuse the same application logic.

Flask supplies routing and integrates Jinja; it does not supply a database
layer or form validation. Its official
[design notes](https://flask.palletsprojects.com/en/stable/design/) describe
those boundaries. Use a production application server behind Caddy under
the [deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/).
Run durable research outside web handlers, consistent with Flask's
[background-task guidance](https://flask.palletsprojects.com/en/stable/async-await/#background-tasks).
Python's documented [SQLite interface](https://docs.python.org/3/library/sqlite3.html)
provides the local database connection. Sources checked on September 24, 2026.

The selected stack still requires concrete choices for request validation,
request protection, migrations, research tools, and job recovery. A small web
framework does not remove those responsibilities. No performance comparison
or capacity benchmark has been run. Reconsider the framework if the desired
browser interactions materially change the balance.

## Newsroom and worker boundary

The accepted [worker design](reporting-worker.md) keeps the newsroom as a
data and coordination service with no AI execution. Workers poll its API for
jobs and context and submit articles or explicit run outcomes. The newsroom
can monitor overdue work without performing the reporting itself.

The [worker host](reporting-worker.md#worker-location) and
[model engine](reporting-worker.md#model-engine-candidates) remain undecided.
Local model execution and GPT-6 Luna through Codex Pro are candidates. The
worker API is separate from whichever model interface is eventually chosen.

## Access boundary

The accepted [audience decision](product-design.md#audience-and-ownership)
makes the reading site public, the newsroom owner-only, and the API
authenticated. Keep public page rendering independent of worker credentials;
Flask can render articles from its database without exposing an anonymous data API.

Accepted on September 25, 2026: use Cloudflare Access for owner browser sign-in
to the newsroom and a dedicated service token for the worker API. Keep reading
pages public. News still enforces the permissions of the authenticated owner
and worker; authentication alone does not authorize every application action.

The owner accepted the recommendation; no further reason was stated. It fits
the existing Cloudflare hosting setup and the KidsBank access pattern. The
tradeoff is a dependency on Cloudflare Access for protected requests and the
need to configure separate owner and worker policies and credentials.

| Surface | Access |
| --- | --- |
| Feed, article pages, and reporter filtering | Public, under the accepted reading requirement. |
| Newsroom, reporter prompts, detailed run history, and management actions | Cloudflare Access browser sign-in restricted to the owner. |
| Worker API | Dedicated Cloudflare Access service token, limited to jobs, history, and result submission. |
| Any other API endpoints | Authentication required; permissions depend on the operation. |

Cloudflare's official
[self-hosted application guide](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
documents browser authentication and access policies. Its
[service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
support automated API access without interactive sign-in. Its
[application-path documentation](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/)
supports policies on selected paths. These capabilities were checked on
September 25, 2026.

The provider is selected; exact policies, identity validation, credential
configuration, and deployment remain implementation work. Cover protected
paths themselves and their descendants. Verify that direct origin access
cannot bypass authentication and that worker credentials cannot authorize
newsroom mutations. Derive application identity from verified authentication,
not arbitrary client-supplied identity headers. Map worker credentials to a
stable logical worker identity so credential rotation need not reset history.
No Cloudflare configuration has been changed for News.

## Email delivery

Accepted on September 25, 2026: use the owner's existing Resend account for
operational alerts, with a separate News sender and a dedicated sending-only
API key. Keep the alert recipient and credentials in deployment configuration,
outside the public repository. The recommended sender is
`News <news@jubishop.com>`; confirm its domain configuration during deployment.

The owner accepted the recommendation; no further reason was stated. Screenr's
`docs/deployment.md` and `.env.example`, reviewed on September 25, 2026, already
describe Resend with a `jubishop.com` sender. This reuses an existing service
while separating News credentials. The tradeoff is that alert delivery depends
on Resend and its account limits. No account settings or credentials have been
changed, and no News email has been sent.

Resend's [API-key documentation](https://resend.com/docs/dashboard/api-keys/introduction)
describes sending-only keys and domain restrictions. Its
[idempotency documentation](https://resend.com/docs/dashboard/emails/idempotency-keys)
supports safely retrying the same email request within a 24-hour retention
window. Sources checked on September 25, 2026. Use a stable notification key
and unchanged email payload for retries, alongside the server's durable
incident state. Provider acceptance is not proof of delivery to the inbox.
Retry handling must account for that 24-hour limit; do not assume indefinite
provider protection against duplicate sends.

The owner selected the recipient on September 25, 2026; keep the address in
private deployment configuration. Use it for the accepted
[backup storage warnings](backups.md) as well.

Email originates from the VPS monitoring service. The later research worker
does not need email credentials. Keep email sending outside article and run
transactions, and retain visible incidents if sending fails. Exact delivery
retry rules, sender verification, provisioning the recipient, and a production
delivery check remain implementation and deployment work.

## Candidates to evaluate

- Persistent reporting state so work can survive restarts. Concurrency,
  supervision, and detailed API contracts remain open within the selected
  process split and worker transport.
- The model engine and research tools under the
  [worker boundary](reporting-worker.md#model-engine-candidates). Do not assume
  a hosted API, Codex, or Ollama is selected.
- SQLite transaction and connection settings for this single-owner application,
  with relatively little concurrent writing. SQLite's official
  [deployment guidance](https://sqlite.org/whentouse.html) supports this usage
  and explains its single-writer constraint. SQLite is selected; remote workers
  must use application operations instead of opening the database over a network
  filesystem.

External documentation checked on September 24, 2026. Choose these components
against News requirements and measured costs. Available integrations or
neighboring application choices do not establish a decision.

## Unresolved implementation decisions

- The shared model, provider integration, research APIs, and reporting interface.
- Supported Python version, package management, and production application server.
- Implement the accepted [database schema](database-schema.md) with migrations,
  and finalize [article validation](server-contract.md#article-payload),
  Markdown rendering, and archive search. Inline images
  load from external URLs; renderer and URL-validation details remain open.
- Independent article deletion and reporter removal, enforcing the
  [no-cascade and recoverable-deletion requirements](product-design.md#independent-article-lifecycle).
- Retaining original reporter IDs and historical attribution after
  [reporter removal](product-design.md#reporter-removal-and-stable-identity).
  Reassignment and inheritance are outside v1.
- Implement attempt configuration snapshots under the
  [accepted editorial workflow](product-design.md#editorial-guidance-through-prompt-edits).
- Durable schedules, run states, retries, publication transactions, and recovery.
  Run records must distinguish published articles, successful
  [empty results](product-design.md#runs-with-nothing-to-publish), and failures.
- Implement the selected [Resend delivery](#email-delivery) for failed-run
  alerts, including delivery failures and duplicate prevention.
- Configure the selected Cloudflare Access authentication, origin enforcement,
  service isolation, credentials, and request protection alongside public reading.
- Implement the accepted [backup policy](backups.md): encrypted R2 snapshots,
  seven daily and four weekly recovery points, restore checks, and a 1 GB email
  warning. Finalize deployment, observability, resource limits, and validation.
