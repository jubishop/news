---
status: current
---

# Reporting worker operations

The Mac worker runs vanilla Codex CLI with GPT-6 Luna and built-in live web
research. Python handles the News API, eight concurrent reporters, durable
results, and retries. A private QMD MCP connection provides
[semantic article history search](article-history-search.md). There are no
worker plugins or paid search API keys. The [worker decisions](reporting-worker.md) explain
this choice and the daily 06:00 Pacific startup.

## Runtime and configuration

Use Python 3.14 and Codex CLI >=0.157.1,<1.0. The worker checks the CLI
version and ChatGPT sign-in before starting research. The CLI executable must
be available unattended; the inspected standalone Mac binary needs no Node
runtime. QMD has its own [runtime and model setup](article-history-search.md#installation-and-checks).
Install from a permanent checkout with `bin/setup` and `bin/app-setup`.
The application adds no new Python dependencies.

Copy [the configuration example](../ops/worker.example.json) to
`~/.config/news/worker.json`. Keep its parent directory mode 0700 and the file
mode 0600. Fill in the dedicated Cloudflare Access service token. Use absolute
paths for `codex` and `state_dir`. Never commit this file or put credentials in
cron. Codex uses the owner's existing ChatGPT sign-in; News strips API keys,
service credentials, and unrelated environment variables from its child.

The shared model defaults to `gpt-6-luna`, medium reasoning, following the
successful pilot. Change `model` in the private config when a supported Luna
alias or new generation is available. A cross-generation Luna `latest` alias
was not documented when implemented; the worker does not invent one or silently
select another model. Ordinary Codex updates supply tool improvements. A new
CLI major version needs compatibility review. The version bounds permit 0.x
updates after 0.157.1; the test suite does not prove every future CLI release.

Codex runs with its personal config, project instructions, skills, plugins,
apps, hooks, memory, browser/computer controls, and subagents disabled. Its only
MCP tools are News history search and article retrieval. Each
attempt gets a private directory. Built-in web research and read-only shell
access remain available. A built-in named permission profile allows shell reads only of the attempt
workspace and minimal system runtime files. Shell network access is disabled;
built-in web research remains available. An offline probe with Codex 0.157.1
verified workspace reading and denial of a file outside the workspace.
The News credential is never included in the prompt, archive, child environment,
or diagnostic log. The supervisor alone authenticates to the News API.

## Daily batch and recovery

Run `bin/worker --config ~/.config/news/worker.json` to process a batch.
`--check` verifies the CLI and QMD versions, ChatGPT login, and authenticated API access
without claiming jobs or calling a model. It does not establish that the
subscription has enough remaining allowance for research.

The worker first acquires an OS file lock. A duplicate start exits without
claiming work. Each research slot starts an independent Python guardian in its
own process session. The guardian launches Codex in a separate process group
and enforces the attempt's deadline, measured from guardian startup. Both
processes inherit the batch lock. The guardian kills the entire research group
on timeout and when Codex exits. It waits for Codex to stop before releasing its lock.
This also stops descendants left behind by a completed Codex process. At most
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
saved pending result receives an explicit replacement claim; a raw Codex output
file alone is not a saved delivery result. Do not remove the lock file or
pending results to recover. If a guardian is also lost, inspect the private
attempt directory and stop its research process group before restarting.

The worker checks in even on an empty day. It claims only when one of eight
slots is available and uses the claim response's exact instruction snapshot.
Paused claims receive `skipped_paused` without starting Codex. A fresh process
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

Accepted on September 26, 2026: Codex has at most 30 minutes per attempt.
The owner considers this sufficient and wants stuck research to stop. Its entire process group is killed
on timeout. Failed processes, invalid JSON, invalid articles, and context-fetch
failures produce explicit retryable failures. A successful empty result stays
distinct from a failed search. Complete valid results are saved before delivery.
The server's six-hour claim duration exceeds the research limit; expiry alone
does not revoke a valid result, so routine renewals are unnecessary.

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

## Private state and diagnostics

Accepted on September 26, 2026: retain detailed research logs for seven days
to support troubleshooting. Private reporting content remains local during
that period. Pending delivery state has separate retention.

The default state directory is `~/.local/state/news-worker`, mode 0700:

- `pending/`: mode-0600 claim requests, ownership tokens, and completed results.
  These are durable delivery state and are never removed by log retention.
- `attempts/`: prompts, Codex JSON events, stderr,
  final candidate output, and receipts. Startup removes logs older than seven
  days, including abandoned attempts. The API receipt remains authoritative.
- `worker.lock`: the process lock. Do not remove it to bypass an active worker.
- `history/`: the latest shared article snapshot, QMD index, and search logs.
  This derived state can be rebuilt; see [history recovery](article-history-search.md#private-state-and-recovery).
- `cron.log`: stdout/stderr from the most recent scheduled batch, overwritten
  each day. Detailed per-attempt logs retain the seven-day history.

Do not paste private prompts, archive content, ownership tokens, or raw logs
into the public issue tracker. The worker saves operation state with atomic
replacement and filesystem synchronization before network mutations. Disk
failure still requires operator recovery; retain the directory for inspection.

## After-merge commissioning

The owner explicitly requested on September 26, 2026 that installing the real
cron job be part of this PR's after-merge work. This immediate deployment and verification belong in the after-merge
handoff. Waiting for the next scheduled run remains separate. Do not install cron from a disposable feature worktree.

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
3. Run `bin/worker --config ~/.config/news/worker.json --check`. Verify API
   authentication and that the service token still fails on owner routes.
   This preflight makes no model call and changes no reporter.
4. Confirm the Mac system timezone is `America/Los_Angeles`, the owner remains
   logged in, and the Mac will be awake at 06:00. Actual macOS cron uses the
   system timezone; setting `TZ` only inside a command does not reschedule it.
   Cron skips a time missed during sleep or shutdown. Existing server catch-up
   handles missed work on the next start. Do not change power settings silently.
5. Preview `ops/install-worker --config ~/.config/news/worker.json`, then run
   the same command with `--install`. The installer checks API access, preserves
   unrelated cron entries, replaces only its marked entry, and reads it back.
   Verify `crontab -l` shows exactly one `0 6 * * *` News entry pointing at the
   permanent checkout. Repeating installation is safe.
6. With no test reporters due, run one normal worker batch to record today's
   real check-in. If real jobs are already due, coordinate the batch with the
   owner's intended first reporting date instead of claiming them as a test.
7. Enable `NEWS_MONITOR_WORKER=true` on the VPS. Set
   `NEWS_MONITOR_START_DATE` to the first expected Pacific check-in date and
   restart News. Preserve other environment values and update the private
   recovery copy. Verify the settings and worker contact in the newsroom.
8. Record the installed cron entry, verified check-in, monitoring start date,
   and any remaining commissioning limitation in the PR and implementation
   issue. Close implementation tracking only after these steps are verified.

The owner's next step is to add reporters scheduled for tomorrow. Inspect the
published articles, reporter outcomes, and private logs after the first 06:00
batch. That later reporting-quality observation is separate from installation.

To disable scheduled runs, remove only the crontab line ending in
`# news-reporting-worker`. Coordinate server monitoring when intentionally
stopping the worker; keep pending results for later delivery.

## Tests

`bin/check-app` includes worker tests. A local mock HTTP server and fake Codex
executable exercise real worker networking, prompts, concurrency, subprocess
handling, persistence, validation, and delivery. Another test uses the actual
Flask/SQLite protocol with fake Cloudflare verification data and a fake Codex
process. Cron tests replace the OS crontab boundary. These tests never call a
paid model, send email, change production data, or install real cron entries.
The crash regression kills a real batch supervisor with SIGKILL while a fake
researcher and its descendant remain alive. It verifies deadline cleanup,
duplicate-start exclusion, unchanged pending state, and a later replacement.

Focused command:

```sh
.venv/bin/python -B -m unittest discover -s tests/app -p 'test_worker*.py' -v
```
