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

## Run the helper

Run from the repository root with Python 3.12–3.14. The local application
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
