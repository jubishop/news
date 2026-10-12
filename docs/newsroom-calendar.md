---
status: current
---

# Upcoming reporting calendar

The newsroom calendar shows active reporting schedules below the reporter
cards. [Issue #23](https://github.com/jubishop/news/issues/23) introduced it,
and [issue #34](https://github.com/jubishop/news/issues/34) revised its
placement and past dates. Each reporter name is a separate link to its
settings and history, including when several reporters share a date. The
calendar also stays available while viewing the retired reporter roster; it
always shows active schedules.

## Placement and past dates

Accepted on October 12, 2026, in the
[October UI review](https://github.com/jubishop/news/issues/30): the calendar
keeps its month grid, but it moves below the reporter cards and stops showing
past dates. The owner chose the recommended option; no further reason was
stated. They chose a calendar option twice: the first choice rested on an
incorrect claim that most reporters were daily, so they chose again once the
real reporter mix was known. Production then had 11 active reporters (nine
weekly, one monthly, and one contractor), and upcoming days held one to three
entries, a density at which the grid shows the weekly rhythm well. The review
found that the calendar, about 900 pixels tall on desktop, pushed the cards
about 1,500 pixels down the page, and that every earlier day was labeled
"Past date", with those rows first in the phone list.

In both roster views, the heading, stat strip, and notices stay at the top,
followed by the roster tabs and reporter cards, then the calendar, then the
operating note. The tradeoff is that the calendar now starts below every card;
its month controls still return to it directly.

Every day of the month stays in the page. The desktop grid shows earlier days
as dimmed cells with only the date number. At widths of 600 pixels or less,
earlier days are hidden, so the current month's list starts at today. When
every day of a month is before today, the calendar says "Past reports for
<Month Year> are in each reporter's history." at every width, in place of the
empty-month message. Cells after a month's last day match the cells before its
first day, so the last week no longer ends in a gray block.

## Reading and navigation

The default month and Today marker use `America/Los_Angeles`, independently
of the browser's timezone. Previous and Next move one month, including across
year boundaries. Today returns to the current Pacific month. The optional
`month=YYYY-MM` newsroom query selects a month directly; invalid values return
the normal validation page with HTTP 422.

Desktop and tablet layouts use a Monday-first month grid. At widths of 600
pixels or less, dates from today onward form a chronological list with weekday
and month labels. All names wrap without truncation. Busy days retain every
link; empty upcoming dates and empty months have explicit messages. Month
controls and reporter links use normal keyboard navigation and work without
JavaScript.

## Schedule and lifecycle rules

This is an upcoming schedule overview, not a record of past reporting.
Dates before today have no entries. Overdue work remains on reporter cards
and in reporter history; the calendar does not move it to another due date.
Paused, removed, and completed reporters are omitted. Pausing or resuming,
editing a schedule, or completing a contractor is reflected on reload.

Today's saved assignments take precedence over the current schedule. Pending,
running, and retry-wait assignments remain visible; finished or skipped runs
stay in history. When today's assignment has not yet been created, the
calendar projects it from the effective schedule. Creating a reporter does
not add it to today, and editing a schedule does not replace today's work.

Future dates use the same cadence rules as assignment creation, starting at
the schedule's effective date. Daily, selected weekdays, monthly, and all
contractor dates are included. Monthly days 29–31 clamp to the last day of a
shorter month, then return to the chosen day in later months. Legacy single
contractor dates remain supported. See the [server scheduling rules](server-contract.md#calendar-pause-and-deletion-behavior)
and [contractor guide](contractor-schedules.md).

Calendar requests only read schedules and today's existing runs. Opening or
navigating the page never creates assignments, advances schedule cursors, or
changes stored configuration. Worker discovery and maintenance keep their
existing responsibilities. No schema change or additional dependency is needed.

## Verification

Owner HTTP journeys check every cadence and reporter link, effective dates,
today's preserved assignment after edits, lifecycle changes, empty months,
leap years, daylight-saving transitions, and month limits. Database snapshots
verify that calendar reads leave all persisted data unchanged. Real Chromium
journeys check month navigation across years, Today in a Tokyo browser,
weekday placement, keyboard access, individual links on a shared day, and
busy days with long names at desktop, tablet, and mobile widths. At 390 and
1440 pixels, they also check that the cards precede the calendar in both
roster views, that earlier days are hidden on phones and dimmed on desktop,
the fully past month message, and the cells after a month's last day.
