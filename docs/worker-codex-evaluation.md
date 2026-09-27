---
status: draft
---

# Codex reporting worker evaluation

On September 26, 2026, the owner reopened the model choice and requested a
comparison with GPT-6 Luna through the existing ChatGPT Pro subscription.
Two actual Codex runs used the exact assignments from the
[local Qwen search pilot](search-evaluation.md). Recommendation: make Codex
with Luna the leading candidate for the first worker. It required less setup
and finished much faster, with better source handling in several respects.
The final engine choice remains open; two reports do not establish reliable
unattended reporting.

## Subscription access and ownership

The installed Codex CLI was already signed in through ChatGPT. Its local model
catalog included `gpt-6-luna`, and both runs completed using that explicit model.
OpenAI documents that [ChatGPT sign-in uses subscription access](https://learn.chatgpt.com/docs/auth),
while API-key authentication uses separate API billing. The pilot forced
ChatGPT authentication and supplied no API keys. It used Codex's built-in web
search and page reader, with no additional search-service account.

[Codex plan usage](https://learn.chatgpt.com/docs/pricing) depends on the model,
context, reasoning, and tools. Subscription limits are shared with other Codex
work. The account's displayed weekly use stayed at 5% before and after these
two runs. This is a coarse account-wide observation, not a task-level charge or
proof of negligible monthly consumption. Token counts cannot be converted
directly into a percentage of the included allowance.

The worker supervisor, schedules, records, and delivery code would remain
project-owned. Model inference and web retrieval would depend on OpenAI and
the subscription. Prompts and supplied archive context would leave the Mac.
Pi/Qwen preserves local inference and more direct choice of search provider,
at the cost of maintaining those integrations and running inference locally.

## Test configuration and limits

- Codex CLI 0.157.1, `gpt-6-luna`, medium reasoning, live web search.
- Same two assignment files, fixed evaluation date, best-effort instructions,
  650-word report limit, and 30-minute process deadline as the Qwen pilot.
- Separate fresh runs, executed sequentially from dedicated evaluation directories.
  Personal configuration, project instructions, skill discovery, shell tools,
  apps, plugins, hooks, memory, browser control, and subagents were disabled.
- Read-only sandbox, no interactive approvals, ephemeral sessions, JSON events,
  and a final JSON schema containing status, Markdown, and source URLs.
- Requested eight individual search queries, ten page-open attempts, and eight
  further reads/finds. These tool budgets were prompt instructions, unlike the
  enforced limits in the Pi pilot. Codex does not expose an equivalent
  five-results-per-query option or the same content slicing controls.

The invocation used `codex exec --model gpt-6-luna --json --ephemeral
--sandbox read-only --output-schema ... --output-last-message ...`, with
`forced_login_method="chatgpt"`, `model_reasoning_effort="medium"`, and
`web_search="live"`. The [non-interactive CLI guide](https://learn.chatgpt.com/docs/non-interactive-mode)
documents structured output and event streaming. Per-run configuration
overrides left the owner's interactive settings unchanged.

This compares complete reporting setups: model, agent harness, search, and
reader. It does not isolate the model or rank Codex's underlying search against
Exa on equal retrieved content. Live search results, query choices, output
length, and page handling varied. Each configuration has only one run per
assignment; no latency distribution or broad quality score is justified.

## Measured results

| Assignment | Pi/Qwen + Exa | Pi/Qwen + Firecrawl | Codex + Luna |
| --- | --- | --- | --- |
| AI model brief | 4m 25s; 588 words | 3m 27s; 497 words | 33.37s; 293 words |
| Family activities | 6m 04s; 553 words | 4m 29s; 831 words | 31.49s; 316 words |

Both Codex processes exited successfully, returned status `report`, and met
the report schema and word limit. The saved assignment files matched the
original pilot inputs byte for byte. Review of completed tool events found
only web-tool use. A warning about the experimental skill-discovery switch
did not prevent either run from completing.

| Codex assignment | Individual search queries | Web-tool batches | Distinct URLs in page-read events | Input tokens | Cached input tokens | Output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| AI model brief | 4 | 3 | 5 | 101,864 | 61,696 | 814 |
| Family activities | 3 | 4 | 11 | 136,394 | 90,112 | 1,044 |

Token counts are the CLI's turn totals. Cached input is included in input,
not an additional charge estimate. Repeated model calls can count earlier
context again; these figures are not the size of a single prompt.

Web batches can contain several queries or page operations. The event stream
labels non-search operations generically and does not preserve every page
operation's arguments or complete returned text. Therefore these URL counts
are not comparable to Pi's reader-attempt counts. The family run returned
eleven distinct page URLs, exceeding the requested ten-URL research budget.
Prompting alone did not enforce that limit.

Read the unchanged [AI draft](evaluations/ai-codex-luna.md) and
[family draft](evaluations/family-codex-luna.md). Raw events, invocation flags,
prompts, schema, and summaries remain in the active checkout's ignored
`.cache/search-pilot/codex-luna/` directory. There was no newsroom submission.

## Source review

### AI model brief

The [OpenAI changelog](https://developers.openai.com/api/docs/changelog)
supports the reported releases, prices, and later image fix.
[Anthropic's announcement](https://www.anthropic.com/claude-opus-5-5)
supports the Opus availability, pricing, and stated restrictions. Luna
attributed performance claims to the vendor and avoided the Qwen/Firecrawl
draft's incorrect API-only availability claim.

Coverage was narrow. All four queries came in one initial batch, including
two restricted to OpenAI and Anthropic. No query explicitly targeted open
models, local inference, Qwen, Hugging Face, or other model publishers.
The report covered two model families and a follow-up fix, while the Qwen
runs found a broader set of publishers. Its statement that no local or
open-weight release was verified is limited to the sources it reviewed;
it does not establish that none existed. The introductory count of two
updates is also awkward beside three bullets.

Assessment: the included technical details held up in the source checks,
but the search strategy needs broader coverage before this is a dependable
model-news reporter. Shorter output and narrower research also contribute
to its faster runtime.

### Family activity shortlist

The [Greek Festival overview](https://seattlegreekfestival.com/) and
[visit page](https://seattlegreekfestival.com/plan-your-visit-2/) support the
year, hours, free admission, children's activities, and rain cover. Neither
cited page states the reservation policy that Luna attributed to the
organizer. That claim should be unknown or separately verified.

The [Fishermen's Festival page](https://www.seattlefishermensmemorial.org/events/fishermens-fall-festival/)
supports its date, admission, and children's activities. Luna correctly left
hours and booking requirements unknown when the page did not supply them.

The [museum visit page](https://seattlechildrensmuseum.org/visit/) supports
the regular hours, prices, extra fee, and reservation statement. The
[calendar page it read](https://seattlechildrensmuseum.org/calendar/list/)
listed events only through October 1. That view did not establish the
absence of special programs on October 3–4, as the draft implied.

Assessment: useful close-in choices, an indoor option, labeled travel
estimates, and generally sound practical details. Two unsupported statements
still need correction. These drafts are not approved for publication.

## Recommended worker direction

Use the existing Python supervisor proposal around a dedicated Codex subprocess
if Luna wins the remaining evaluation. Keep claims, archive mediation, the
30-minute deadline, durable candidate storage, validation, delivery retries,
and seven-day research-log retention outside the model. The daily start stays
at 01:00 Pacific. Changing the engine does not require a newsroom API change.

Codex removes the immediate need to select and maintain a Pi research extension,
search account, and local reader for the first worker. The tradeoffs are cloud
inference, shared subscription limits, less direct control of retrieval, and
CLI/model changes. Keep the Pi/Qwen results as a comparison, without silently
switching models or buying API capacity when subscription access is unavailable.

Before enabling unattended publication:

1. Repeat the two assignments with broader source coverage and explicit
   claim-to-source checks. Verify missing details stay unknown and calendar
   pagination is not treated as evidence of absence.
2. Test a representative longer reporter assignment and archive context.
   Keep private assignment text and personal details out of this public repo.
3. Measure several ordinary batches alongside interactive Codex use. Record
   account usage and failures without treating a flat percentage as zero cost.
4. Test expired authentication, exhausted allowance, tool failure, malformed
   results, process timeout, and saved-result delivery recovery. Subscription
   authentication worked in this headless pilot; it is not an availability
   guarantee for an unattended service.

No scheduler or production worker was installed by this evaluation.
