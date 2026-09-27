---
status: draft
---

# Research additions for a Codex worker

This September 26, 2026 comparison answers whether plugins or MCP servers
could improve the [Codex worker candidate](worker-codex-evaluation.md).
Recommendation: keep built-in web search as the baseline and test additions
that supply missing evidence or source-specific data. Firecrawl is the first
ready-made integration to evaluate. No addition is selected for production.

MCP is a standard interface for giving an agent tools. A plugin can package
those tools with instructions. Neither is an additional model by definition.
[Codex supports local and remote MCP servers](https://developers.openai.com/codex/mcp),
including tool allow lists and timeouts. That lets the worker expose only the
research operations it needs. An app connection must still be verified in
the isolated, non-interactive worker configuration; the pilot deliberately
disabled personal plugins and configuration.

## Candidates and incremental value

### Firecrawl: page extraction and scientific papers

The official [Firecrawl MCP](https://docs.firecrawl.dev/mcp-server) supports
keyless use within daily limits and authenticated account access. Use it as a
fallback reader when built-in retrieval cannot supply a useful page, and test
its dedicated paper tools for scientific reporters.

Its [Research Index](https://docs.firecrawl.dev/features/research) returns paper
records, source identifiers, abstracts, relevant full-text passages, and
related papers. It covers biomedical sources including PubMed, bioRxiv, and
medRxiv, plus arXiv. Dedicated research tools differ from the ordinary web
search research-category filter. Date filters concern created/updated dates;
the reporter must still check publication dates and distinguish preprints
from peer-reviewed work.

[Published pricing](https://www.firecrawl.dev/pricing) lists Research Index
paper endpoints as free, including life sciences. The account free tier
includes 1,000 monthly credits for other operations. Basic page scraping uses
one credit per page; advanced operations can cost more. The $19 monthly Hobby
plan exceeds the owner's approximate $10 search budget. Keyless daily limits
and account monthly credits are distinct.

A direct keyless paper-search probe returned two records with identifiers and
abstracts. This was an API access check, not an installed-plugin test or a
health-report evaluation. Earlier Firecrawl reader probes retrieved two pages
blocked to Pi's local reader; they do not establish an advantage over Codex's
reader. The next trial must compare against Codex directly.

Expose only page/document reading and the paper search, metadata, passage-read,
and related-paper tools initially. Hosted autonomous research and recurring
monitor tools would add separate behavior and cost beyond this proposal.

### Direct PubMed / Europe PMC tools: structured literature access

For scientific reporters, a small project-owned adapter can retrieve paper
identifiers, abstracts, metadata, and available open full text directly.
This gives more explicit control over evidence and date filtering than a
general web query. PubMed metadata does not imply full-text access.

NCBI's [E-utilities guidance](https://eutilities.github.io/site/API_Key/usageandkey/)
permits up to three requests per second without a key. The
[Europe PMC API](https://europepmc.org/RestfulWebService) also offers structured
search and article retrieval; one public search returned a full metadata
record without credentials during this review. A narrowly scoped wrapper
would fit the project's preference for owned, focused integrations, but it
would be code we must maintain. No particular third-party PubMed MCP package
has been audited or selected.

### Hacker News: stories and discussion threads

The [official HN API](https://github.com/HackerNews/API) provides story and
comment records, timestamps, scores, and parent/child relationships through
public endpoints. Algolia provides [HN search](https://hn.algolia.com/api).
A small adapter could search discussions and then retrieve a bounded comment
tree. This is a useful complement for technology reporters that need to
separate an announcement from community reaction. It requires pagination,
comment limits, and correct treatment of deleted items; it does not provide
Reddit or X access.

### Exa or Tavily: an alternate search provider

Both are available in the plugin directory. Exa's
[official MCP](https://exa.ai/docs/get-started/exa-mcp) supports free,
rate-limited keyless access and authenticated usage, with domain and date
controls. An alternate index could find sources missed by Codex, but the
paired pilot has not established an improvement over built-in search.

Keep these as optional search comparisons rather than adding both to every
report. The earlier Exa burst returned rate limits. The
[provider comparison](worker-research-comparison.md) covers keyed free tiers
and conditional paid options. A free MCP connection is not unlimited service.

### Playwright: interactive websites

Microsoft's [Playwright MCP](https://github.com/microsoft/playwright-mcp) can
operate a local browser, including headless and isolated sessions. It could
inspect calendars or ticket pages whose details require JavaScript or clicks.
The software has no hosted search fee, but adds browser installation,
resource use, and more interaction steps. Use it only for a demonstrated
retrieval gap, with a separate worker browser profile. A browser does not
guarantee access through login requirements or site restrictions.

### Consensus: a packaged academic-search alternative

Consensus is available in the plugin directory. Its
[API/MCP guide](https://help.consensus.app/en/articles/16516328-the-consensus-api)
describes research search and a shared allowance of 30 calls per month on the
free plan. That is enough for a small comparison, but limited for several
recurring reporters. Do not confuse unlimited paper searches in its web app
with the MCP allowance. Prefer testing the free Firecrawl paper endpoint or
direct literature APIs first. No Consensus account was connected here.

## Reddit and X

An MCP wrapper does not create data access that its underlying service lacks.
[Reddit's Data API](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data)
requires approved access. [X's API pricing](https://docs.x.com/x-api/getting-started/pricing)
currently charges $0.005 per ordinary post read. That makes 2,000 such reads
$10 before any other billed resources. Neither is equivalent to unlimited
free social search. General web discovery remains useful, but indexed posts
do not establish complete thread access or coverage.

## Recommended comparison

Compare built-in-only Codex with the same Luna configuration plus narrowly
enabled Firecrawl reader and paper tools. Keep assignment, dates, history,
report length, and attempt deadline fixed. Add a synthetic literature brief
and a page known to need more retrieval work. Inspect source support,
publication dates, preprint status, citation links, missing details, tool
failures, latency, and provider usage. A successful API response alone is
not evidence of better reporting.

Add direct HN access if discussion coverage is part of the technology
assignment. Consider direct PubMed/Europe PMC access when structured clinical
literature queries are needed. Retain an addition only when the comparison
shows useful evidence or materially less missing information.

The [Luna pilot](worker-codex-evaluation.md#source-review) also found unsupported
statements despite readable sources. Better retrieval must be paired with
claim-to-source checks; adding more tools alone does not address that failure.
No plugin was installed, persistent MCP configuration changed, or new
reporting run scheduled during this research.
