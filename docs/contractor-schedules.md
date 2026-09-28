---
status: current
---

# Contractor assignment dates

A contractor has a finite list of distinct Pacific calendar dates. It uses one
Contractor option in the newsroom; a single date is the simplest case. This
extends the original one-time contractor design under
[issue #16](https://github.com/jubishop/news/issues/16), accepted September 28,
2026. There is no fixed product limit on the number of dates. The normal
request-size limit still applies.

The owner wants several specific reporting dates without creating a recurring
reporter or a separate contractor for each date. Missed dates should not cause
several research executions in succession. These rules supersede the original
single-date restriction and retirement after the first successful result.

## Editing dates

Create, view, and edit the date list in the newsroom with one native calendar
picker per future date. **Add another** adds a blank entry and focuses its
picker. **Delete** removes that entry and moves focus to the next entry, the
previous entry, or **Add another** when none remain. Both controls work with
the keyboard and change only the form. Use **Add reporter** or **Save changes**
to persist the dates. This interface implements
[issue #18](https://github.com/jubishop/news/issues/18).

Duplicate dates are rejected and saved dates are sorted. Blank entries are
ignored; a new contractor still needs at least one date. Each new date must be
after today in Pacific Time, regardless of the browser's timezone. Future dates
can change or be removed. Once a date is due, retain it and its history; only
its instructions can change. Due dates appear separately with an explanation
and no edit or delete controls. Removing the last future entry is allowed when
due dates remain; the completion rules below still apply.

The preview updates when a date changes or an entry is added or removed. It
shows the first future date, a validation message, or the existing explanation
that unfinished assignments remain due when no future dates remain.

The September 25 schedule rule remains: edits preserve today's work and take
effect tomorrow. This avoids requiring a result before the daily worker can
discover it. The fixed-date rule preserves assignment identity and history.
The owner accepted both recommendations without a further stated reason.
Contractors cannot become recurring reporters; create a new reporter to change
category. This avoids changing completion rules during an active assignment.

## Catch-up and completion

At discovery, combine unfinished due dates into one execution. Include today
when it is scheduled, and leave future dates pending. Reuse the latest eligible
scheduled run, retaining its original due date. Earlier unstarted work becomes
`superseded`, linked to that run. Earlier failed runs retain their failures and
attempts. An attempt already underway takes precedence and keeps its original
scope; dates that become due while it runs wait for later work.

For October 1, 3, and 5 assignments:

- A worker returning October 4 runs once for October 1 and 3. October 5 remains.
- A worker returning October 5 runs once for all three dates.
- If October 1 exhausts its retries, a successful October 3 execution satisfies
  both dates. October 5 remains, and the October 1 failures remain in history.

Publication and `nothing_to_publish` both satisfy the included dates. Retire
only when no future or unresolved dates remain. Removing the last future date
after all due work succeeded also finishes the contract. Retain the reporter,
articles, original due dates, and attempts. Failure, lateness, and pause
acknowledgments do not satisfy dates or cause retirement.

The September 25 no-expiration decision still applies: overdue work stays
available within its retry allowance. Instructions determine coverage and
usefulness. The worker may return a successful empty result if the assignment
is no longer useful. The server never derives an article coverage interval
from assignment dates.

## Retries and pause

Each execution keeps the existing three-attempt allowance and retry delay.
Rechecking on another day does not create a new catch-up identity or replenish
retries. A later scheduled date provides its own bounded allowance; success
also satisfies earlier failed dates, including exhausted ones.

When no later date remains, changed instructions reopen the final failed,
unresolved date with a fresh bounded generation. Earlier failed dates keep
their outcomes and are included in that retry's scope. A later future date or
an unfinished later run prevents earlier failures from reopening. The original
runs and earlier attempts remain. Unchanged saves, renames, and pause/resume
cannot reset the allowance.
Dates already satisfied by later success do not reopen. The owner accepted
instruction-edit recovery September 25 without a further stated reason. It
permits correction without a Run Now control, at the cost of requesting new
work whenever failed instructions change.

Pause acknowledgments record contact and keep unfinished dates. On resume,
combine unfinished due dates by the same catch-up rule. A valid attempt
started before a pause or removal can still deliver its result. Replaying an
accepted result returns its receipt without duplicate runs or articles.
Recurring scheduling and its pause behavior remain unchanged.

## Persistence and verification

New schedules use `{"cadence":"once","dates":["2026-10-01","2026-10-03"]}`.
Legacy `date` schedules are read as one-element lists. Stored attempt snapshots
and receipts are not rewritten. No schema migration is needed: due dates cannot
be removed or added retroactively, and a later successful run satisfies every
earlier date. The greatest successful run date therefore establishes which
assignments remain. This is completion accounting, not a research coverage
cursor. History reports the satisfying run separately from earlier outcomes.

The [server contract](server-contract.md) specifies the form and API fields.
HTTP journeys cover catch-up, retries, edits, pause, retained history, legacy
data, and idempotency. Browser journeys cover calendar entries, keyboard
add/delete controls, validation, preview, future edits, removal of the last
future date, and retained history at desktop and mobile widths. A worker integration
test uses the real supervisor and server with fake external research.
