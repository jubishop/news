---
status: draft
---

# Reporting examples

These reference assignments make the [product design](product-design.md)
concrete and provide examples for evaluating the reporting engine. They are
generalized requirements, not copies of private reporter prompts or completed
reports. Store personal configuration in the application database rather than
the public repository; public articles are a separate output from that
configuration.

## Weekly family activity shortlist

Provided by the owner on September 24, 2026 as an existing scheduled task.
It runs each Thursday at 08:00 Pacific Time and recommends activities for
the upcoming weekend. The purpose is practical family planning, not simply
summarizing events that happened since the previous run.

The 08:00 time describes the existing task. Under the
[day-based scheduling decision](product-design.md#schedules-by-day) accepted
on September 25, 2026, News stores Thursday as the reporting day and leaves
the execution time to the worker.

### Assignment requirements

- Produce a fresh, concise shortlist of five Seattle-area family activities.
  Tailor suitability to the children's ages from private family context.
- Evaluate travel from the configured starting point under realistic weekend
  conditions. About two hours each way is an outer limit, not a target. Prefer
  nearby options, and explain why any distant option merits the extra travel.
  Do not add distant options merely for geographic variety.
- Include a seasonal mix of events, exhibits, performances, indoor recreation,
  exploration, attractions, and occasional outdoor walks. Hiking must not
  dominate. Deprioritize beach-focused outings. Give indoor options substantial
  weight in cold or wet weather, and avoid unsuitable outdoor recommendations.
- Use earlier shortlists to rotate recommendations. Repeat a recent option
  only for a compelling new reason.
- Research current sources on each run. Prefer official venue, event, park,
  land-manager, weather, and transportation sources. Recent Washington Trails
  Association reports can supplement an outdoor recommendation.
- Explain why each option is particularly worthwhile that weekend, using
  supported event dates, seasonal details, or forecast conditions. Do not
  invent a timely reason or claim verification that did not occur.
- Include approximate travel time, outing duration, and useful dates, hours,
  prices, booking, parking, and access details. Account for ferry waits where
  relevant. For walks and hikes, include distance, elevation gain, difficulty,
  and material trail conditions or closures.
- Link directly to useful sources. Distinguish forecasts from confirmed
  conditions. State the weekend dates in Pacific Time. Rank the strongest
  option first, accounting for travel effort, and keep the whole list easy to
  scan.

The owner supplied the task as a concrete example of desired reporting.
Its relevance is the combination of current research, personal preferences,
practical constraints, and memory across runs. The tradeoff is that a concise
output can still require substantial research and verification.

### Implementation implications

These are engineering deductions from the example, not additional accepted
product choices:

- Interpret the reporting day in `America/Los_Angeles`, including across
  daylight-saving changes. The server does not configure or enforce 08:00;
  worker-side execution timing is a separate choice.
- Supply the run date and timezone to the reporter. The assignment controls
  the relevant date window; this report targets the coming weekend rather
  than only events since the previous run.
- Preserve detailed assignment text. A topic label such as "family activities"
  would lose material constraints and preferences.
- A single article containing five ranked entries is a natural representation
  of this assignment. It must not force every other reporter into that format.
- Retrieve enough prior coverage to identify individual recommendations.
  Summaries that omit the venues or activities would not support rotation.
- Support research across multiple sources and reading relevant source pages.
  Discovery snippets alone may omit booking, closure, or access details.
- Keep preference rules distinct from strict limits. For example, a preference
  for official sources does not prohibit useful recent trail reports.

### Proposed evaluation cases

Use this example to evaluate the complete reporting flow, including:

- A Thursday run produces coverage for the correct upcoming weekend.
- Runs before and after a daylight-saving change remain assigned to Thursday
  in Pacific Time, regardless of the worker's chosen execution hour.
- Prior recommendations are available and a repeated pick has a supported
  new reason.
- The report favors nearby activities and explains exceptional longer travel.
- Forecasts and unavailable details are represented honestly.
- The stored article can be rendered in another layout without rerunning
  research.

Schedule, persistence, and tool-boundary behavior need automated tests.
Editorial quality also needs review of representative generated reports;
passing schema checks alone cannot establish the usefulness of the shortlist.

### Open questions exposed by this example

- What happens when research supports fewer than the requested five picks?
- Which missing practical details are acceptable with a clear caveat, and
  which gaps should prevent an option or an entire report from publication?
- How much prior coverage should be included, and what counts as a recent pick?
- How should delayed or missed runs handle a weekend that is already underway
  or over?
- What research duration and cost are acceptable for this level of detail?

## Research updates after missed runs

Provided by the owner on September 25, 2026: a reporter follows new research
about a subject, such as cholesterol. It normally reports weekly, but missed
runs can make the gap longer. The assignment needs to express "since your
last report" using actual coverage history rather than a fixed seven-day
lookback. This is a scheduling and coverage example, not medical guidance.

The accepted [coverage rules](product-design.md#reporting-memory-and-coverage-window)
and [catch-up policy](reporting-worker.md#missed-recurring-runs-and-catch-up)
govern the behavior. The worker interprets the prompt and retrieves history
as useful. The server records the coverage span submitted on each article;
it does not select a research window. A successful empty run remains visible
as an outcome without implying a server-calculated coverage span.

### Proposed evaluation cases

- A weekly reporter misses two scheduled runs. The worker uses the prompt and
  retained history to select the full gap and submits one catch-up result.
  Repeated discovery does not create duplicate catch-up work.
- Failed, missing, paused, and successful empty outcomes stay distinct in run
  history. None causes the server to fabricate or advance coverage dates.
- A research article submitted on September 25 specifies September 1 through
  September 24. The server stores and returns those supplied dates unchanged,
  even though the expected reporting date or publication date differs.
- Archive filters use the stored coverage dates. A future weekend span is also
  valid; the server must not replace it with a retrospective research window.
- A new reporter has empty history. Its prompt and the worker determine the
  first report's span without a server-selected lookback.

Automated server tests can verify supplied metadata, retrieval, and outcome
states using deterministic fixtures. Whether the worker selects and actually
covers the right span requires representative reporting runs in the later
worker phase. Correct metadata storage cannot prove research completeness.
