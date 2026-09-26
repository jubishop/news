---
status: draft
---

# Backups and storage warnings

This page records the accepted backup policy for News. The server has not
been implemented or deployed.

## Accepted policy

Accepted on September 25, 2026: adopt Screenr's encrypted off-server R2 backup
approach, retaining seven daily and four weekly snapshots. Keep automatic
restore checks. Alert the owner by email when the complete News backup bucket
exceeds 1 GB (1,000,000,000 bytes), measured after a successful backup and
retention cleanup. Continue backups and keep the retention policy unchanged.

Send one warning for each continuous period above the threshold. A successful
measurement below it permits another warning on a later crossing. Equality
neither starts nor clears a warning. Send through the selected
[Resend service](implementation-design.md#email-delivery), with the owner's
selected recipient stored in private deployment configuration.

The owner wants useful recovery history without surprise storage costs.
Keeping only the latest backup was considered and withdrawn after inspecting
Screenr's small storage use. Retention limits history, but neither retention
nor this warning imposes a hard spending cap.

## Server implementation requirements

- Use a dedicated private R2 Standard bucket and scoped object credentials.
  Keep the backup encryption password recoverable outside the VPS.
- Create a consistent SQLite backup using SQLite's backup API or an equivalent
  supported snapshot operation. Do not copy a live database file alone when
  committed changes can still be in its write-ahead log.
- Back up the database containing reporters, articles, runs, and operational
  state. Article images remain external URLs; do not archive image files.
- Keep seven daily and four weekly recovery points. Restic may count one
  snapshot toward both groups and deduplicates shared content. Do not assume
  there must be exactly eleven separate full database copies.
- Measure all pages of objects in the dedicated bucket, including encrypted
  data and repository metadata. Retain the latest successful measurement and
  warning state durably. A failed check must not appear as zero usage or clear
  an existing warning.
- Persist notifications before sending. Retry with a stable key and unchanged
  payload, respecting the provider's duplicate-prevention window. Preserve a
  visible incident when measurement or delivery fails.
- Run a weekly restore check in an isolated temporary location. Validate
  database integrity and representative queries, then remove the temporary
  restored data. Never restore a test over the running database.

These are implementation requirements; exact timer settings, package/runtime
versions, secret provisioning, and restore-check queries remain engineering
work. Backups and warnings run on the VPS independently of the AI worker.

## Cost boundary

Cloudflare's [R2 pricing](https://developers.cloudflare.com/r2/pricing/), checked
September 25, 2026, includes 10 GB-month of Standard storage per account each
month. Usage above the free allowance is billable; the allowance is not a
hard stop. Storage billing uses average daily peaks over the billing period.
Other applications share this allowance, and request charges have separate
limits.

The News warning measures its retained bucket contents after cleanup. It
does not measure account-wide usage, incomplete multipart uploads, or temporary
upload peaks. Keep account usage under review as applications grow. This
decision authorizes a warning and the stated retention, not a paid storage
upgrade or a guaranteed zero-cost cap.
