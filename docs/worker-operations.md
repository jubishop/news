---
status: current
---

# Reporting worker operations

The Mac worker runs the Claude Code CLI with Claude Haiku 5.5 and Claude
Code's built-in web search and fetch. Python handles the News API, eight
concurrent reporters, durable results, and retries. A private QMD MCP
connection provides [semantic article history search](article-history-search.md).
There are no worker plugins or paid search API keys. The
[worker decisions](reporting-worker.md) explain this choice and the daily
06:00 Pacific LaunchAgent.

The worker can also send immediate [macOS failure notifications](failure-alerts.md)
for final reporter failures and local operational errors. This optional local
delivery adds no server polling and leaves server email alerts unchanged.

## Runtime and configuration

Use Python 3.14 or later and Claude Code 2.1.296 or later. The worker checks the CLI
version and the Claude subscription login before starting research. Install
Claude Code with its official installer; the native Mac binary needs no Node
runtime. QMD has its own [runtime and model setup](article-history-search.md#installation-and-checks).
Install from a permanent checkout with `bin/setup` and `bin/app-setup`.
The application adds no new Python dependencies.

Copy [the configuration example](../ops/worker.example.json) to
`~/.config/news/worker.json`. Keep its parent directory mode 0700 and the file
mode 0600. Fill in the dedicated Cloudflare Access service token. Use absolute
paths for `claude` and `state_dir`. Never commit this file or put credentials
in the LaunchAgent.

Claude Code uses the owner's existing subscription login, which it keeps in
the macOS keychain. The worker must therefore run in the owner's login
session. On October 9, 2026, the CLI reported "Not logged in" under cron and
completed a model call from a LaunchAgent. News strips API keys, OAuth tokens,
service credentials, and unrelated environment variables from its child, so
research cannot silently switch to API billing. Preflight requires the
`claude.ai` subscription login method.

The shared defaults are `claude-haiku-5-5` and high effort, following the
[model decision](reporting-worker.md#model-engine). `model` and `effort` in the
private config override them; `effort` accepts `low`, `medium`, `high`,
`xhigh`, or `max`. Use a documented model identifier when changing models.
The worker does not invent aliases or select a fallback model. It rejects a
config that still contains the Codex-era `codex` or `reasoning_effort` keys.
Claude Code updates itself through the owner's interactive sessions; the
worker disables the updater in its own child so the CLI does not change during
a batch. The worker accepts new major versions under the latest stable
[version policy](foundation/engineering-policy.md#runtime-and-toolchain-versions);
the test suite does not prove every future CLI release.

Each attempt runs `claude --print` in restricted mode from a private attempt
directory. Restricted mode ignores user, project, and local settings, so
personal plugins and hooks do not load. It removes the shell and other
code-running tools and confines file tools to the attempt directory. The
worker enables only Read, Glob, Grep, WebSearch, and WebFetch, plus News
history `query` and `get`. It hides QMD's other tools, and `dontAsk`
permission mode denies anything else. `--strict-mcp-config` loads only the
News history server. Slash commands and skills are disabled, subagents are
unavailable, and sessions are not saved. Environment switches also disable
instruction files such as `CLAUDE.md` and `AGENTS.md`, auto-memory, and the
Git status snapshot. The default state directory sits inside the owner's home
Git repository, and that snapshot otherwise reaches the model. Claude Code's
default system prompt and built-in plugins remain.

Probes with Claude Code 2.1.296 on October 9, 2026 verified these boundaries.
A file outside the workspace was denied. A canary `AGENTS.md` and `CLAUDE.md`
in a parent directory reached the model only with both restricted mode and
the instruction-file switch removed. The News credential is never included in
the prompt, archive, child environment, or diagnostic log. The supervisor
alone authenticates to the News API.

## Daily batch and recovery

Run `bin/worker --config ~/.config/news/worker.json` to process a batch.
`--check` verifies the CLI and QMD versions, Claude subscription login, and
authenticated API access without claiming jobs or calling a model. It does not establish that the
subscription has enough remaining allowance for research.

The worker first acquires an OS file lock. A duplicate start exits without
claiming work. Each research slot starts an independent Python guardian in its
own process session. The guardian launches Claude Code in a separate process group
and enforces the attempt's deadline, measured from guardian startup. Both
processes inherit the batch lock. The guardian kills the entire research group
on timeout and when Claude Code exits. It waits for Claude Code to stop before
releasing its lock. This also stops descendants left behind by a completed
Claude Code process. At most
eight research attempts run at once; guardians do not create extra slots.

If the batch supervisor dies, including from SIGKILL, each guardian keeps its
original deadline. Research can finish within the remaining time, but cannot
hold the lock indefinitely because the batch supervisor is gone. A replacement
batch skips while the inherited lock remains held. After all guardians and
research groups stop, the next start can acquire the lock. This protects
against batch supervisor death; it does not supervise a guardian that is itself
forcibly killed or suspended.

The batch supervisor still validates and saves complete results before delivery.
Guardians do not call the News API or change pending state. On restart, saved
pending results are delivered before discovery or replacement research. An
identical submission returns the original server receipt. An attempt without a
saved pending result receives an explicit replacement claim; a raw Claude Code
event log alone is not a saved delivery result. Do not remove the lock file or
pending results to recover. If a guardian is also lost, inspect the private
attempt directory and stop its research process group before restarting.

The worker checks in even on an empty day. It claims only when one of eight
slots is available and uses the claim response's exact instruction snapshot.
Paused claims receive `skipped_paused` without starting Claude Code. A fresh process
gets the original due date, reporting day, current Pacific timestamp, recent
run outcomes, and the reporter's latest 20 stored article summaries with their
coverage dates. The batch refreshes the archive manifest once, downloads only changed or missing
articles, and shares one validated private QMD index across all reporters and retries. Reporters search related
coverage and read selected articles through bounded tool responses. The
[history-search guide](article-history-search.md) defines snapshot freshness,
index maintenance, runtime requirements, and failure handling.

The assignment determines coverage. There is no computed lookback or special
morning cutoff. Best effort permits useful partial reporting. Prompts require
source checks and clear uncertainty, but tests cannot establish factual quality.

Accepted on September 26, 2026: each research attempt has at most 30 minutes.
The owner considers this sufficient and wants stuck research to stop. Its entire process group is killed
on timeout. Failed processes, invalid JSON, invalid articles, and context-fetch
failures produce explicit retryable failures. A successful empty result stays
distinct from a failed search. Complete valid results are saved before delivery.
The server's six-hour claim duration exceeds the research limit; expiry alone
does not revoke a valid result, so routine renewals are unnecessary.

Claude Code streams JSON events to the attempt log. Its final `result` event
carries the schema-validated draft in `structured_output`. The worker accepts
a draft only when that event reports success and the startup event shows the
News history server connected. Codex refused to start research without that
connection; Claude Code continues without it, so a lost connection costs one
attempt and becomes a retryable failure. A missing or unsuccessful final event
is also a retryable failure.

The output schema and shared instructions require `article_date`,
`coverage_start`, and `coverage_end` as Pacific calendar dates (`YYYY-MM-DD`).
If a completed draft instead supplies an ISO timestamp with an explicit UTC
offset or `Z`, the worker converts that instant to a Pacific date before
validation. It retains the original draft in `result.json`. Missing offsets,
unknown `-00:00` offsets, invalid dates, and reversed coverage ranges still fail.
Validation failures include the specific contract error in the run history so
later attempts can correct it. Other research failures retain private diagnostics.
The server continues to accept dates only.

An exhausted recurring run does not reopen on worker restart. For operator-led
recovery of a retained draft, first validate the corrected result and confirm
its reporter, original assignment, and failed-run receipt. Acquire the worker
lock, preserve pending state, and take a consistent private server database
backup. Reopen only the verified failed run with a new retry generation, keeping
all prior attempts. Claim a fresh attempt through the worker API, save its
ownership and corrected result durably, and submit through the normal result
endpoint. Verify the receipt, article contents, and resolved incident. Reuse
the saved claim and submission IDs after an uncertain response; never replay a
different result against a finished attempt or insert articles directly.

HTTP calls have a 30-second timeout and up to three attempts with the same
payload. Redirects are refused so credentials do not follow an unexpected
origin. After an unsuccessful delivery, pending state remains on disk and the
worker exits nonzero. Other reporters continue. The next startup retries saved
results before research. Do not delete pending state to retry a publication.
Malformed archive pages become explicit research failures. A damaged pending
record or a per-run storage error is reported without stopping other reporters;
the affected state is retained for operator repair.

Research retries use the server's three-attempt allowance. The batch waits
15 minutes and five seconds between retry rounds, then rediscovers only its
failed original jobs. This delay releases process slots after each round and
avoids early claims. It does not continuously discover new daily assignments.
Exhausted or nonretryable failures stay visible on the server. Restarting during
a server retry delay can defer that work to the next daily batch. This is
acceptable daily discovery behavior; use an explicit local start for earlier
recovery if needed. A crash during unfinished research creates an explicit
replacement attempt when the assignment is next offered.

## Shared article writing guidance

The [shared reporter prompt](../news/worker_claude.py) applies to every research
attempt alongside the reporter's assignment. On September 30, 2026, the owner
requested a shorter, general wrapper that trusts the writer's judgment. Beat
requirements belong in each reporter's prompt; the wrapper leaves coverage,
structure, emphasis, and length to the assignment and editorial judgment.

The shared principles retain the clarity goal from
[issue #21](https://github.com/jubishop/news/issues/21): clear titles and summaries,
plain language, useful context, checked sources, and honest uncertainty. Past
articles supply context without dictating style. History search, failure
handling, workspace boundaries, and the output contract remain shared rules.
Search tactics and article structure are not prescribed.

For [issue #25](https://github.com/jubishop/news/issues/25), the shared prompt
also asks reporters to find and include photos or illustrations when they help
the reader. Use the existing [inline image format](server-contract.md#inline-images):
direct HTTPS image URLs in the Markdown body, descriptive alt text, and a nearby
source credit and link. Image selection remains an editorial judgment.

Few reports had images, so on October 9, 2026 the owner asked for photos in
many stories and chose an explicit [lead photo](product-design.md#structured-article-storage).
The prompt names visual subjects that usually deserve a photo, such as games,
products, events, places, and people in the news. It asks for a `lead_image`
with alt text and a linked credit, and for further body photos where they help,
such as one per roundup entry. Abstract research usually gets none. It
suggests official and press pages and Wikimedia Commons, and asks reporters to
request a page's image URLs while fetching it. Reporters must use only image
URLs they found, never invented or guessed ones.

An unusable lead photo, such as one with a non-HTTPS URL or an empty credit,
is dropped rather than failing the result. Before saving a result, the
supervisor requests each lead and inline image URL as a browser would, without
a referrer, and follows only HTTPS redirects. It never requests non-HTTPS
destinations, which the page would not show. It keeps images that return a
successful image response. Access denials, rate limits, server errors, and
timeouts are inconclusive, since bot protection can refuse scripts that
browsers pass, so those images also stay. It removes the rest, such as missing
files, unknown hosts, web pages, and non-HTTPS destinations: a failed lead
photo becomes none, and a failed inline image's Markdown is deleted. Each attempt's private
`images.json` records the outcome per URL. Reference-style Markdown images are
not checked; the page removes them if they fail to load.

The automated worker test verifies that this guidance reaches the Claude Code process
alongside the exact claimed assignment. The worker/server integration test also
verifies that lead photos, image Markdown, and credits survive publication and
render on the public pages. Worker tests fake image hosts to verify that images
that fail to load are removed. These tests do not measure generated prose or image quality,
establish factual accuracy, or guarantee external image availability.

Updating the permanent worker checkout after merge activates the guidance for
new attempts. Server deployment alone does not update the Mac worker. Published
articles and already saved results retain their original text.

## Private state and diagnostics

Accepted on September 26, 2026: retain detailed research logs for seven days
to support troubleshooting. Private reporting content remains local during
that period. Pending delivery state has separate retention.

The default state directory is `~/.local/state/news-worker`, mode 0700:

- `pending/`: mode-0600 claim requests, ownership tokens, and completed results.
  These are durable delivery state and are never removed by log retention.
- `attempts/`: prompts, the MCP configuration, Claude Code stream-JSON
  events, stderr, the structured draft in `result.json`, and receipts. Startup removes logs older than seven
  days, including abandoned attempts. The API receipt remains authoritative.
- `worker.lock`: the process lock. Do not remove it to bypass an active worker.
- `history/`: the latest shared article snapshot, QMD index, and search logs.
  This derived state can be rebuilt; see [history recovery](article-history-search.md#private-state-and-recovery).
- `scheduled.log`: stdout/stderr from the most recent LaunchAgent batch,
  replaced at each scheduled start. Detailed per-attempt logs retain the
  seven-day history. The retired `cron.log` is no longer written.

Do not paste private prompts, archive content, ownership tokens, or raw logs
into the public issue tracker. The worker saves operation state with atomic
replacement and filesystem synchronization before network mutations. Disk
failure still requires operator recovery; retain the directory for inspection.

## After-merge commissioning

The owner explicitly requested on September 26, 2026 that installing the real
scheduler be part of the original worker PR's after-merge work. Installation
and its immediate verification belong in the after-merge handoff; waiting for
the next scheduled run remains separate. Do not install from a disposable
feature worktree.

After the PR is merged and its full checks pass:

1. Confirm the merged commit and successful server deployment. Update the
   permanent `/Users/jubi/projects/news` checkout to that reviewed `main`
   revision without disturbing unrelated work. Run `bin/app-setup` there if
   its environment is missing or dependencies changed.
2. Commission the dedicated Cloudflare **Service Auth** token for the News API
   application. The server-only deployment currently denies API access. Keep
   the owner application's audience and policy separate. Use the private
   [hosting record](../memory/production-hosting.md) for provider configuration
   locations. Save the new token only in mode-0600 worker configuration.
3. Confirm `claude auth status --text` shows the owner's Claude subscription.
   Run `bin/worker --config ~/.config/news/worker.json --check`. Verify API
   authentication and that the service token still fails on owner routes.
   This preflight makes no model call and changes no reporter.
4. Confirm the Mac system timezone is `America/Los_Angeles`, the owner remains
   logged in, and the Mac will usually be awake at 06:00. launchd uses the
   system timezone and starts a 06:00 run missed during sleep after the Mac
   wakes. It does not replay a start missed while the Mac is off or the owner
   is logged out. Existing server catch-up handles missed work on the next
   start. Do not change power settings silently.
5. Preview `ops/install-worker --config ~/.config/news/worker.json`, then run
   the same command with `--install` while no batch is running. The installer
   runs `--check` and refuses while a batch holds the worker lock. It removes
   only the cron entry ending in `# news-reporting-worker`, preserving other
   cron jobs. It then writes `~/Library/LaunchAgents/com.jubishop.news.worker.plist`
   and loads it with `launchctl bootstrap`. Verify that
   `launchctl print gui/$(id -u)/com.jubishop.news.worker` shows the 06:00
   calendar interval and the permanent checkout. Verify that `crontab -l`
   has no News entry. Repeating installation is safe; it reloads the agent
   only when its definition changed.
6. With no test reporters due, run one normal worker batch to record today's
   real check-in. If real jobs are already due, coordinate the batch with the
   owner's intended first reporting date instead of claiming them as a test.
7. Enable `NEWS_MONITOR_WORKER=true` on the VPS. Set
   `NEWS_MONITOR_START_DATE` to the first expected Pacific check-in date and
   restart News. Preserve other environment values and update the private
   recovery copy. Verify the settings and worker contact in the newsroom.
8. Record the installed agent, verified check-in, monitoring start date,
   and any remaining commissioning limitation in the PR and implementation
   issue. Close implementation tracking only after these steps are verified.

The owner's next step is to add reporters scheduled for tomorrow. Inspect the
published articles, reporter outcomes, and private logs after the first 06:00
batch. That later reporting-quality observation is separate from installation.

### Moving an installed worker from Codex and cron

An existing installation keeps its service token, server monitoring, history
snapshot, and pending results. After the Claude Code change merges, perform
steps 1, 3, 4, and 5 above. Before step 3, edit the mode-0600 private config:
replace `codex` with the absolute `claude` path (`~/.local/bin/claude` from
the official installer), set `model` to `claude-haiku-5-5`, and replace
`reasoning_effort` with `effort`. Step 5 retires the cron entry. Delete the
old `cron.log` only after it is no longer needed. Observing the next 06:00
batch is separate from this immediate migration.

To disable scheduled runs, run
`launchctl bootout gui/$(id -u)/com.jubishop.news.worker` and remove
`~/Library/LaunchAgents/com.jubishop.news.worker.plist`. Coordinate server
monitoring when intentionally stopping the worker; keep pending results for
later delivery.

## Tests

`bin/check-application` includes worker tests. A local mock HTTP server and fake
Claude Code executable exercise real worker networking, prompts, concurrency,
subprocess handling, persistence, validation, and delivery. Another test uses
the actual Flask/SQLite protocol with fake Cloudflare verification data and a
fake Claude Code process. Installer tests replace the `launchctl` and crontab
boundaries and write the agent into a temporary home directory. These tests
never call a model, send email, change production data, or load real
LaunchAgents or cron entries.
The crash regression kills a real batch supervisor with SIGKILL while a fake
researcher and its descendant remain alive. It verifies deadline cleanup,
duplicate-start exclusion, unchanged pending state, and a later replacement.

Focused command:

```sh
.venv/bin/python -B -m unittest discover -s tests/app -p 'test_worker*.py' -v
```

Fake executables cannot establish Claude Code's real flags, structured output,
or MCP behavior. On October 9, 2026, two real attempts with Claude Code 2.1.296
and Haiku 5.5 ran through this worker's research function. They used the
synthetic [history fixture](../tests/fixtures/article-history.json), the real
QMD MCP server, and a state directory inside the home Git repository. Each
searched News history, used live web search and fetch, and returned a
published draft that passed result validation, in 76 and 78 seconds. The
second run used the final tool list, with no permission denials. These two
runs do not establish Haiku's reporting quality, factual accuracy, or
behavior across many reporters.
