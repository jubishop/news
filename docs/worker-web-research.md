---
status: draft
---

# Free web research for the worker

This September 26, 2026 research supports the [local worker proposal](worker-runtime.md).
It separates the accepted cost constraint from search and tool recommendations.
The worker's [selected Qwen model](reporting-worker.md#model-engine) generates
search queries, reads tool results, and writes reports. A separate search tool
actually contacts search services and returns sources to the model.

## Accepted cost and ownership constraint

Accepted on September 26, 2026: the owner requires the solution to be free
and under their ownership or control. They are open to approaches that meet
those conditions and requested advice about how Qwen should search.

Do not introduce a paid search subscription, metered API spending, automatic
paid fallback, or a trial that later requires payment. Free software on existing
hardware still uses power, network access, and maintenance time. The tradeoff
is that free search services can impose quotas, change access, or block requests.

Clarified on September 26, 2026: an API key and external service are acceptable
when a free tier supports this relatively small personal workload. The owner
accepted controlling the worker and integration while using external search.
Keyless access is convenient, not a requirement. No account or subscription
has been created during this discussion.

## Selected integration and alternatives

Accepted on September 26, 2026: start with Pi, `pi-web-access`, and Exa's free
keyless search. The owner accepted the recommended option; no further reason
was stated. This avoids a separate search service to operate and keeps Qwen
local. The tradeoff is reliance on Exa's availability and free-access limits.
The owner's API-key clarification permits evaluating keyed free tiers if
needed; it does not select another provider or authorize paid usage.

The subsequent [extension comparison](worker-research-comparison.md) examines
15 published packages, including the other research extensions the owner named.
It retains `pi-web-access` as the leading trial candidate, with explicit
limitations. This comparison does not establish superior report quality or
complete the required installed-extension evaluation.

Qwen reasons and writes locally. The extension sends a query to Exa and returns
results, then reads relevant pages. This supplies the search tool that hosted
agents commonly provide out of the box. The model does not gain search ability
merely because its host has an internet connection.

The owner asked whether the Mac can simply search Google. It can, through a
browser tool or a search adapter. The agent needs that tool to issue the query
and return results. A browser-based Google route is possible, but search-page
changes, consent screens, or bot challenges make it less convenient for an
unattended first version. A documented tool interface is the simpler starting
point. This is an engineering recommendation, not a claim that Google access
is impossible or that every search API requires payment.

SearXNG remains an alternative if a locally operated search service becomes
useful. It is a free, self-hostable metasearch engine: it combines other engines'
results rather than maintaining its own web index. Its [project documentation](https://docs.searxng.org/)
and [private-instance guide](https://docs.searxng.org/own-instance.html) explain
that operating model. It adds a service to maintain and still depends on
upstream engines and public websites.

| Option | What we control | Limits and fit |
| --- | --- | --- |
| Private SearXNG | Local service, engine selection, integration, and updates. | No search API bill with free engines. Extra service maintenance; upstream blocking remains possible. Alternative if operating the search service becomes necessary. |
| Exa's keyless MCP endpoint | Worker and client code; Exa owns the search service. | No API key required. Selected initial route. Quotas and continuity remain external. |
| Ollama's free web search | Worker and client code; Ollama owns the search service. | Requires an account and API key. A documented free tier exists, with rate limits. Possible if a free account is acceptable. |
| Direct DuckDuckGo HTML search | Local search adapter; DuckDuckGo owns the search service. | No search API subscription, but page format changes and bot challenges can interrupt unattended research. Secondary candidate. |

[Exa advertises keyless MCP access](https://exa.ai/mcp).
[Ollama documents free-account web search](https://ollama.com/blog/web-search)
and its [search/fetch API](https://docs.ollama.com/capabilities/web-search).
Neither statement establishes unlimited nightly capacity or permanent free
availability. A quota exhaustion must defer or fail research, never trigger
billing. Free tiers must be verified again before deployment.

Exa's keyed API is a different cost path from its free keyless limits. Adding
a key is not an approved remedy for exhausted free access. The comparison
also identifies Tavily, Brave, and Firecrawl's recurring free allowances;
Tavily is the proposed next provider evaluation if Exa is insufficient.

SearXNG's [search API](https://docs.searxng.org/dev/search_api.html) supports JSON
when enabled in the instance. Its [limiter documentation](https://docs.searxng.org/admin/searx.limiter)
explains that upstream engines can return CAPTCHAs or block the instance.
Self-hosting is control over the software, not an availability guarantee.
No usable SearXNG installation or container runtime was established during
this inspection. Compare installation options before choosing a host runtime.

For known news sources, direct feeds and official source pages can supplement
search without an API bill. They reduce search dependence but do not replace
open-ended discovery for assignments such as local activities. Source selection
must remain assignment-driven rather than a hidden fixed list of allowed beats.

## Pi integration

The selected [pi-web-access](https://github.com/nicobailon/pi-web-access)
extension supplies the research tools. It supports SearXNG, keyless Exa,
Ollama, DuckDuckGo, and local content extraction. The [inspected package source](https://github.com/nicobailon/pi-web-access/blob/main/package.json)
reported 0.31.0; an installed release has not been tested with News.

Use `workflow: "none"` for raw search results. Explicitly restrict providers,
disable browser-cookie access and interactive review, and avoid hosted-model
summaries. Reject tool arguments that request other workflows or providers.
Disable unnecessary cloning and video paths. The worker must not inherit the
owner's personal provider keys or browser sessions. Read the pinned release's
actual configuration and fallback behavior before relying on these controls.

The useful loop is simple:

1. Qwen proposes a query from the reporter's assignment and prior coverage.
2. The search tool obtains candidate URLs and snippets from the approved service.
3. A reading tool fetches relevant pages and extracts their text locally.
4. Qwen compares the evidence, follows up where needed, and prepares a cited report.
5. The Python supervisor validates and saves the result before publication.

Keep the search and reading interfaces narrow enough to replace the provider
without changing the newsroom. If the extension's dependency and configuration
cost is too high for these needs, compare a small News adapter to the selected
search interface plus a maintained page-text extractor. Do not build an independent
web index or treat snippets as verified source content.

## Evidence still needed

Use public or synthetic assignments to compare source relevance, date accuracy,
full-page retrieval, blocked pages, per-run request counts, and total duration.
Exercise rate-limit handling before relying on a free search route unattended.
The local Pi/Qwen tool-use probe did not contact any search provider and cannot
establish the quality or reliability of these options.
