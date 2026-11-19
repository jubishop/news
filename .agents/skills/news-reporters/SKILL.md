---
name: news-reporters
description: Create, inspect, edit, pause, resume, or delete reporters and contractor schedules in the News production newsroom. Use for reporter administration, not changes to the reporting worker or application code.
disable-model-invocation: false
---

# Manage News reporters

Make the owner's requested reporter changes, and only those, with the
[helper](scripts/reporters.py), which runs the deployed application's reporter
functions on the VPS over SSH. Run
`.agents/skills/news-reporters/scripts/reporters.py --help` for its commands,
connection defaults, reporter fields, schedule rules, and errors.

## Choose the reporter and assignment

List reporters before creating or changing one, and `show` one to read its
instructions, schedule, and status. Resolve an ambiguous target with the
owner, and reuse an existing reporter when the request is an edit.

For a new reporter, turn the request into clear instructions about the topic,
coverage period, useful sources, and expected report. Research event dates
when the schedule depends on them, as Pacific calendar dates, including
daylight-saving changes. Report unknown event dates instead of inventing them.

## Coverage and reporting history

For recurring news and research prompts, prefer coverage since the end of the
reporter's last successful report's stated coverage period through the current
research time. Cover gaps from missed or failed runs. Give each prompt an
explicit first-report window suited to the assignment, such as the past seven
days for a weekly news review. Keep coverage windows and research cutoff
timestamps out of article titles, summaries, and bodies; the worker records
coverage dates as article metadata. Start the body with the story. Keep dates
that are part of the story, such as event dates, release dates, and the
weekend for an activity shortlist. Apply this guidance when creating prompts
or editing their coverage rules; preserve the owner's explicit time windows
and unrelated instructions.

Use the researched period, not the publication or run-completion time, as the
boundary. A successful "nothing to publish" result can establish that boundary
only if its recorded explanation makes the researched period clear. If the
boundary is uncertain or only a calendar date is available, search an
overlapping period and remove repeats. Failed runs and pause acknowledgments
do not establish coverage. The worker interprets these instructions; the
server does not compute research windows. See the
[coverage rules](../../../docs/product-design.md#reporting-memory-and-coverage-window).

The worker already searches
[article history](../../../docs/article-history-search.md) before choosing
stories; assignment wording should say how the beat uses it. Avoid repeating
prior coverage, but include material new findings, corrections, or other
developments and explain what changed. New coverage of an old finding does
not by itself make the finding new. For recommendation lists, consult prior
lists and follow the owner's rules about repeats.

Keep calendar and event windows when they define the task: a previous month's
book releases, activities for an upcoming weekend, or recaps of assigned games.
Use history checks within those rules rather than changing eligibility dates
or replacing them with a rolling news window.

## Run the helper

Pass reporter JSON through a private file or stdin, never interpolated into a
shell command, and keep private requests out of Git. Instruction changes can
reopen exhausted contractor work under the
[contractor rules](../../../docs/contractor-schedules.md). Deletion cancels
unstarted work but keeps articles, history, and results from an attempt
already underway.

## Verify and recover

Report the resulting schedule and any meaningful limitations. When the helper
reports a stale version or an unknown outcome, read the reporter again before
any retry and reconcile the owner's request with what is saved. Don't restore
the helper's pre-change backup over the whole database on your own; that could
overwrite later work.

The helper doesn't retry runs. To retry a reporter's failed latest run, follow
[retrying failed runs](../../../docs/worker-operations.md#retrying-failed-runs).

Use the owner's normal administrative SSH access; the restricted deployment
key cannot run this helper. Consult the
[hosting record](../../../memory/production-hosting.md) if the helper can't
reach the VPS, and don't change authentication or deployment setup to complete
reporter administration.
