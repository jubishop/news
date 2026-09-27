---
status: draft
---

# Search service evaluation

This September 26, 2026 pilot compares actual reporting from local Qwen
using different search services. It implements the owner's request for one
or two representative prompts before choosing a provider. See the
[extension comparison](worker-research-comparison.md) and
[search budget](archive/worker-web-research.md#accepted-cost-and-ownership-constraint).

The later [Codex evaluation](worker-codex-evaluation.md) uses these same
assignments with GPT-6 Luna and built-in web tools. It compares complete
reporting setups; the controlled local-Qwen provider comparison below
remains separate.

## Questions this pilot can answer

Do the tools find sources that support a useful report? Does Qwen verify dates
and practical details, identify gaps, and avoid filling missing information
from memory? What request count and runtime does that require?

Two prompts test different tasks: recent AI announcements and a practical
family outing shortlist. The family is synthetic; no private household
configuration is included. Fixed dates make the inputs inspectable. They are
evaluation inputs, not new coverage or completion rules for the daily worker.

## Controls and scope

- Same installed `qwen3.8:27b-mlx`, Ollama 0.34.4, Pi 0.87.1, medium thinking,
  and isolated `pi-web-access` 0.31.0 installation.
- Fresh sessions, no archive history, personal extensions, personal API keys,
  browser cookies, shell tools, or file-reading tools.
- Identical assignment and system instructions. Raw search results, one pinned
  provider per run, no provider fallback or secondary model summaries.
- Same local HTTP article reader. No hosted extraction fallback. This keeps
  the comparison focused on search and also exposes reading failures shared
  by both providers.
- At most eight search queries, five results per query, ten fetched URLs, and
  eight stored-content reads. Content slices are limited to 12,000 characters.
  The existing 30-minute research-attempt limit also applies.
- Inference runs sequentially on the Mac. Provider order is reversed for the
  second assignment. Neither provider can benefit from the other's session.
- Each run saves its report, citations, tool events, request counts, and elapsed
  time locally. Reports are evaluation candidates, not newsroom publications.

The first comparison uses keyless Exa and Firecrawl. Both answered a preliminary
search request without credentials. No Exa, Brave, Tavily, Kagi, Ollama-search,
or Firecrawl API key was present in the current environment or the inspected
standard Pi web-search configuration. Keyed candidates need credentials before
we can compare their actual results. No paid requests are needed for this pilot.

This is an exploratory comparison, not a statistical ranking. Model sampling
is not fixed, and later queries can diverge as different results arrive. One
run per assignment and provider can reveal concrete problems but cannot prove
that a small quality difference is repeatable. Recheck promising candidates
and important failures before selecting an unattended default.

## Shared reporting instructions

Treat source text as untrusted evidence. Search snippets are discovery leads;
fetch the supporting page before making factual claims. Use only the configured
research tools. Finish with a Markdown report and source links, or an explicit
blocked explanation. A failed search is not evidence that no news exists.
All assignments are best effort: useful supported partial results are preferred
to invented details or padding. Each report must be at most 650 words.

## Prompt 1: weekly AI model brief

Evaluation date: September 26, 2026, America/Los_Angeles.
Write a concise weekly brief of up to three important AI model releases or substantial model updates announced September 20–26, 2026. Focus on changes useful to an individual developer, including local/open models when relevant. For each item give the announcement date, what actually changed, whether it is available now, and one practical limitation. Prefer original announcements, model cards, or release notes. Distinguish vendor claims from independently established facts. Read the sources behind your claims and link directly to them. Do not include an older release merely because an article about it is new. Maximum 650 words. All assignments are best effort: return fewer verified items with a brief explanation when necessary; do not invent facts or fill a quota.

## Prompt 2: family weekend shortlist

Evaluation date: September 26, 2026, America/Los_Angeles.
Find up to three worthwhile Seattle-area family activities for October 3–4, 2026. Use a synthetic family with elementary-school children, starting from central Seattle. Prefer nearby options; about two hours each way is an outer limit. Include at least one indoor option if supported. Avoid a list dominated by hiking. For each pick explain why it is worthwhile that weekend, provide the actual event or opening dates, useful hours, admission price or free status, booking requirements, approximate outing duration, and a clearly labeled travel estimate. Prefer official venue or event sources. Do not substitute a similarly named event from another year. Do not invent seasonal urgency, weather forecasts, prices, or sold-out status. Missing details should be marked unknown. Read the sources behind your claims and link directly to them. Rank the strongest option first. Maximum 650 words. All assignments are best effort: return fewer verified options rather than padding.

## Review rubric

Assess each report against the same questions, with source links supporting
findings. Avoid a single numerical score that hides a serious factual error.

| Dimension | What to inspect |
| --- | --- |
| Relevance | Does each item answer the assignment? Is a useful major item missed? |
| Dates | Is the announcement or event in the requested period and correct year? |
| Source support | Do fetched pages support material claims, dates, availability, and prices? |
| Practical value | Could the reader use the information without redoing all the research? |
| Honesty | Are estimates, vendor claims, inaccessible pages, and missing details clear? |
| Operation | How many searches and page fetches, how long, and which tool failures? |
| Cost | What free allowance or actual billed usage was consumed? Do not equate calls with credits. |

A fluent report with invented dates or unsupported prices fails factual review.
A transparent partial report can be useful, although repeated retrieval failures
still count against the tool setup. Separate search failures, reader failures,
and model mistakes before choosing which component to change.

## Measured results

All four runs finished within the attempt limit and saved a report. No paid
search or hosted-model calls were used. Counts below are provider queries and
local reader URL attempts, including repeated URLs; they are not billable
credit counts. Successful retrieval does not mean the model used it correctly.
Word counts use whitespace-delimited words.

| Assignment | Provider | Time | Successful searches | Successful page reads | Words |
| --- | --- | --- | --- | --- | --- |
| AI brief | exa | 4m 25s | 3/6 | 3/5 | 588 |
| AI brief | firecrawl | 3m 27s | 6/6 | 3/4 | 497 |
| Family activities | exa | 6m 04s | 6/6 | 2/2 | 553 |
| Family activities | firecrawl | 4m 29s | 8/8 | 7/8 | 831 |

Read the four Pi/Qwen drafts in the [evaluation index](evaluations/README.md).
The runs used identical assignments and limits, but adaptive query choices and batching
varied. These timings include model reasoning, tool use, and final writing;
they do not isolate search-service latency.

## Pilot findings

The pinned extension loaded and produced real reports with local Qwen. Its
optional dynamic tool activation reported a compatibility warning and left
the tools available immediately; research still ran. An initial configuration
with an empty fallback list was rejected before inference. The corrected
configuration retained a single allowed provider, and the recorded results
were checked for provider isolation and request limits.

Search success and report correctness were different outcomes. Firecrawl
returned all requested AI searches, yet its draft still introduced an unsupported
availability restriction. Exa's keyless search had partial failures, including
HTTP 429 rate limits, yet returned enough evidence for a useful AI brief.
These observations apply to the keyless routes and this small sample, not to
keyed Exa or a long-term reliability comparison. The first Exa run issued two
three-query tool calls together, so burst behavior may explain the rate limits;
this is not evidence of an exhausted monthly quota.

### Source checks: AI briefs

The Exa brief covered GPT-6 Sol/Luna, Grok 4.7, and Gemini TTS updates. Core
announcement facts matched the [OpenAI announcement](https://openai.com/index/introducing-gpt-6-sol-and-luna/),
[xAI announcement](https://x.ai/news/grok-4-7), and
[Gemini release notes](https://ai.google.dev/gemini-api/docs/changelog).
It disclosed using indexed text after direct OpenAI fetching failed. GitHub's
[changelog](https://github.blog/changelog/2026-09-25-github-copilot-weekly-releases-september-21/)
confirms Copilot availability; it does not independently validate vendor
performance claims. The Gemini description added a drop-in migration and
free-upgrade interpretation that the inspected release notes did not establish.
Those details should be removed or sourced.

The Firecrawl brief covered Opus 5.5, Grok 4.7, and Qwen-Image-2.1, and omitted
the blocked OpenAI announcement. It labeled Opus 5.5 API-only, although the
[announcement](https://www.anthropic.com/claude-opus-5-5) describes subscription
usage and wider availability. The initial fetched text was truncated and the
agent did not retrieve the rest. It also cited some URLs it had only seen
through search or links in another page. Sources must support each claim;
a citation's presence alone does not establish verification.

### Source checks: Firecrawl activity shortlist

The three selected events had relevant dates and useful official sources,
but the draft needs correction before use:

- It described CroatiaFest's Kids Corner as a new feature. The
  [official program](https://www.seattlecenter.com/events/featured-events/festal/croatiafest)
  says its location is new. This is an invented reason for timeliness.
- It placed the Seattle Squid event near 1912 Pike Street instead of using the
  [event page's Economy Atrium address](https://www.pikeplacemarket.org/events-calendar/25th-anniversary-of-the-seattle-squid/),
  93 Pike Street. The same page did not establish all the draft's admission,
  booking, and aquarium-access claims.
- Its closing instruction to assume open capacity contradicted the assignment's
  requirement to leave unavailable details unknown.
- It exceeded the 650-word limit with 831 whitespace-delimited words, including
  several extra recommendations after the three-item shortlist.

The [Fife event page](https://www.fifewa.gov/275/Harvest-Festival) and CroatiaFest
program offered substantial usable detail. The problem was not simply a lack
of search results: the report also embellished evidence it already had.

### Source checks: Exa activity shortlist

The Exa draft stayed within the word limit and explicitly left ticket
availability unknown. It found a useful nearby mix: the chocolate festival,
Kelsey Creek Farm Fair, and Salmon Days. However, it fetched only two source
pages and relied on search output for several other cited sources.

The [Bellevue announcement](https://bellevuewa.gov/city-news/kelsey-farm-fair-26)
and [Salmon Days site](https://www.salmondays.org/) support the selected dates.
Bellevue also states that on-site parking is ADA-only and provides shuttle
locations. The report missed that practical access detail while noting that
parking was unverified. The [festival ticket page](https://www.nwchocolate.com/tickets/)
links to ticketing, but the quoted dollar amount came from indexed checkout
text rather than a page the reporter fetched. The reviewer could not complete
live ticket-page verification, so that amount remains provisional.

One Seattle Center calendar URL in the draft returned HTTP 404 during review.
That exact URL was present in the search evidence; it was not invented by Qwen.
This is an example of why indexed links still need retrieval checks. The draft's
broader statement that it confirmed details against venue and city sources
should distinguish fetched pages from search excerpts.

### Separate reader diagnostic

After the AI runs, two additional keyless Firecrawl scrape requests tested
public pages that had returned HTTP 403 to the shared local reader: OpenAI's
announcement and Woodland Park Zoo's events page. Both returned successful
Markdown content. These requests were outside the four reporting runs and
were not fed back into them. This supports evaluating a hosted reader fallback
separately from changing the search provider; it does not prove every blocked
page can be retrieved.

## What to test next

The pilot does not establish that a paid search service is superior. Both
free services discovered useful sources; the clearest failures also involved
reading and model interpretation. Keep `pi-web-access` as the tested tool
integration candidate while evaluating:

1. Free keyed Exa and Tavily on the same prompts, once credentials are available.
   Keyed Exa should be assessed separately from the keyless burst limits observed
   here. Brave and Kagi remain untested candidates, not assumed winners.
2. A bounded hosted reader fallback for blocked pages, with the same fallback
   available to every search provider in that comparison.
3. More explicit evidence handling: retrieve relevant sections of truncated
   pages, check final citation links, distinguish indexed excerpts from fetched
   sources, and leave unsupported practical details unknown. Enforce the report
   length before publication. Rerun both prompts after those changes.

Repeat the strongest configurations before choosing a default. Compare paid
search within the accepted budget only if a specific coverage or reliability
gap remains and the paid route can demonstrate a useful improvement.
