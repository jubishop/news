---
status: current
---

# Local failure notifications

The Mac worker can send immediate native notifications for failures it detects
locally. Enable this optional feature in the worker configuration. Server-only
incidents continue to use the existing
[email behavior](server-operations.md#monitoring-and-email).

## Notification scope

Accepted on October 1, 2026: notify only for failures detected on this Mac,
immediately. This supersedes the earlier choice to mirror every email alert
and the proposed background polling. The owner narrowed the scope to avoid
polling and its added complexity. No separate agent or recurring check is needed.

## Behavior

A failed reporting attempt produces a notification after the existing result
submission confirms that the run has reached its final failure. Attempts that
will retry remain quiet. The result receipt includes the accepted `run_state`,
so this requires no extra API request. The notification names the reporter and
scheduled date; clicking opens that reporter in the authenticated newsroom.
Private research details stay in the logs and run history.

Worker startup and operational errors caught after configuration loads produce
an immediate local worker notification. These do not require a working API or
valid service credentials. Repeated worker errors remain quiet until a batch
finishes without operational errors. Final reporter failures do not prevent
that reset: the worker itself can operate correctly while research fails.

The worker keeps notified attempt IDs and worker-error state in
`alerts/seen.json` under its private state directory. A lock coordinates parallel
reporters; atomic mode-0600 writes preserve duplicate tracking across restarts.
The native notification group also stays the same when an attempt is replayed.
Keep this file when updating the worker. Deleting it can repeat old notices.

Delivery is best effort. Native notification failure is logged and cannot change
the reporting outcome or block saved-result delivery. There is no background
delivery retry. A crash between native delivery and saving its local record can
repeat a banner; the group replaces the existing notification. macOS notification
permissions and Focus settings control presentation and sound.

This is not a scheduler or machine monitor. It cannot notify when the Mac is off,
the scheduler never starts Python, configuration cannot be read, or a process is
forcibly killed. Server email continues to detect missing worker contact.

## Enable after merge

Deploy the server first so new result receipts include `run_state`, then update
the permanent Mac checkout. Older saved receipts remain unchanged; a retryable
failure in an old receipt cannot establish finality for a desktop notification.
Do not run the production worker from a disposable worktree.

Install [terminal-notifier](https://github.com/julienXX/terminal-notifier) if it
is missing. The inspected Mac has version 3.1.0. Add its absolute executable
path to the mode-0600 `~/.config/news/worker.json`:

```json
"terminal_notifier": "/opt/homebrew/bin/terminal-notifier"
```

Omitting this setting disables desktop notifications. No Python dependency is
added. Using the existing native helper provides clickable notifications and
delivery errors without maintaining an application bundle ourselves. The helper's
[documented options](https://github.com/julienXX/terminal-notifier#usage) were
checked on October 1, 2026; actual desktop presentation needs a live check.

Send a clearly labeled setup notification and allow notifications when macOS
asks. Use `terminal-notifier -diagnose` to inspect permissions. Verify the banner
and its newsroom link from the logged-in desktop. This check does not need a
real failed reporter. The worker uses the default notification sound and respects
Focus; it does not request a bypass. The existing 06:00 cron schedule is unchanged.

## Automated checks

The tests run the real worker against the Flask/SQLite server with fake Codex,
QMD, and notifier executables. They verify that retryable attempts stay quiet,
final failure notifies, result receipts replay consistently, local startup errors
deduplicate and rearm, and notifier errors do not escape into reporting. They do
not send real notifications, run a paid model, or change the user's configuration.
