---
name: news-reporters
description: Create, inspect, edit, pause, resume, or delete reporters and contractor schedules in the News production newsroom. Use for reporter administration, not changes to the reporting worker or application code.
user_invocable: true
disable-model-invocation: false
---

# Manage News reporters

Carry out the owner's requested reporter changes directly on the VPS through
SSH. Use the bundled [helper](scripts/reporters.py), which calls the deployed
application's reporter functions. Browser interaction is unnecessary for this
workflow. Keep changes within the owner's request.

## Choose the reporter and assignment

List reporters before creating or changing one. Use `show` to inspect an
existing reporter's instructions, schedule, status, ID, and `config_version`.
Resolve an ambiguous target with the owner. Reuse an existing reporter when
the request is an edit; the helper rejects duplicate active names.

For a new reporter, turn the request into clear instructions about the topic,
coverage period, useful sources, and expected report. Research event dates
when the schedule depends on them. Use Pacific calendar dates, including
daylight-saving changes. Report unknown event dates instead of inventing them.

## Coverage and reporting history

For recurring news and research prompts, prefer coverage since the end of the
reporter's last successful report's stated coverage period through the current
research time. Cover gaps from missed or failed runs. Give each prompt an
explicit first-report window suited to the assignment, such as the past seven
days for a weekly news review. Use Pacific Time and put coverage dates in the
article's `coverage_start` and `coverage_end` metadata. Do not add coverage
windows or research cutoff timestamps to article titles, summaries, or bodies.
Start the body with the story. Keep dates that are part of the story, such as
event dates, release dates, and the weekend for an activity shortlist.
Apply this guidance when creating prompts or editing their coverage rules;
preserve the owner's explicit time windows and unrelated instructions.

Use the researched period, not the publication or run-completion time, as the
boundary. A successful "nothing to publish" result can establish that boundary
only if its recorded explanation makes the researched period clear. If the
boundary is uncertain or only a calendar date is available, search an overlapping
period and remove repeats. Failed runs and pause acknowledgments do not establish
coverage.
The worker interprets these instructions; the server does not compute research
windows. See the [coverage rules](../../../docs/product-design.md#reporting-memory-and-coverage-window).

Ask reporters to search their available article history before choosing stories.
Avoid repeating prior coverage, but include material new findings, corrections,
or other developments and explain what changed. New coverage of an old finding
does not by itself make the finding new. For recommendation lists, consult prior
lists and follow the owner's rules about repeats. History search is already part
of the [worker's shared behavior](../../../docs/article-history-search.md);
assignment wording should clarify how to use it.

Keep calendar and event windows when they define the task: a previous month's
book releases, activities for an upcoming weekend, or recaps of assigned games.
Use history checks within those rules rather than changing eligibility dates
or replacing them with a rolling news window.

## Run the helper

Run from the repository root with Python 3.14 or later. The local application
environment supplies a supported interpreter:

```sh
.venv/bin/python .agents/skills/news-reporters/scripts/reporters.py list
.venv/bin/python .agents/skills/news-reporters/scripts/reporters.py show REPORTER_ID
.venv/bin/python .agents/skills/news-reporters/scripts/reporters.py create --data /private/path/reporter.json
.venv/bin/python .agents/skills/news-reporters/scripts/reporters.py update REPORTER_ID --if-version 3 --data /private/path/changes.json
.venv/bin/python .agents/skills/news-reporters/scripts/reporters.py pause REPORTER_ID --if-version 4
```

`resume` and `delete` take the same arguments as `pause`. `list --all` includes
completed and deleted reporters. Use the actual ID and version from `show`.
Pass JSON through a private file or `--data -` on stdin; do not interpolate
instructions into shell commands. Keep private requests out of Git.

Creation requires `name`, `prompt`, and `cadence`, plus the schedule fields below.
An update supplies only changed fields and preserves the rest. Schedule arrays
replace their saved arrays; retain due contractor dates when editing the list.

| Cadence | Additional fields |
| --- | --- |
| `daily` | None |
| `weekly` | `weekdays`: list of `mon` through `sun` |
| `monthly` | `day_of_month`: integer from 1 to 31 |
| `once` | `dates`: list of distinct `YYYY-MM-DD` dates |

New schedules take effect tomorrow in Pacific Time. New contractor dates must
be after today; due dates remain fixed. A reporter cannot switch between
recurring and contractor categories. Instruction changes can reopen exhausted
contractor work under the existing [contractor rules](../../../docs/contractor-schedules.md).
Deletion retires the reporter and cancels unstarted work while preserving
articles, history, and results from an attempt already underway.

## Verify and recover

The helper uses the current deployed release as the `news` OS user. It takes
a consistent, mode-0600 database backup before each mutation, applies the
change in a transaction, and reads the configuration back through a fresh
connection. Its JSON result includes `before`, `after`, `backup_path`, and
`verified`. Report the resulting schedule and any meaningful limitations.

Each mutation replaces the previous helper backup at
`/var/lib/news/reporter-backups/reporters-before-change.sqlite3`. This is a
local recovery snapshot, separate from the regular encrypted backups. Do not
restore the whole database automatically; that could overwrite later work.

If the helper reports `stale_version`, read the reporter again and reconcile
the requested change. If SSH loses the reply or times out, the write may
have committed. Inspect `list` and `show` before deciding whether to retry;
do not repeat a mutation blindly. The helper does not retry writes.

Connection defaults are in `--help`. Consult the
[hosting record](../../../memory/production-hosting.md) if infrastructure changes.
Use the owner's normal administrative SSH access; the restricted deployment
key cannot run this helper. Do not change authentication or deployment setup
to complete reporter administration.
