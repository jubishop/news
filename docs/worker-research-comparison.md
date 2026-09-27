---
status: draft
---

# Pi research extension comparison

Research checked on September 26, 2026 for the [local reporting worker](worker-runtime.md).
The recommendation remains a constrained `pi-web-access` trial. Evaluate
Exa's free keyed plan first; its documented allowance strengthens this option. This is a comparative engineering judgment, not a measured finding
that it produces better reports. The [accepted cost constraint and initial
selection](worker-web-research.md) remain authoritative.

## Scope and method

Screened 15 published npm packages, including a superseded package name.
Read package documentation, manifests, and relevant search, extraction, and
configuration code. Retrieved published artifacts without installing packages
or running their setup scripts. Versions below identify the inspected releases;
repository links can change after this review.

The criteria are useful source text, local Qwen compatibility, unattended
operation, bounded model context, maintenance cost, and the accepted budget.
Free remains preferable; paid search must justify its cost against free results.
The worker has one local 27B model and a 30-minute attempt limit. An extension
that makes several model calls can use Qwen, but those calls still consume
local inference time. Relative runtime and report quality need measurement.

All inspected manifests declare MIT licenses. That gives control over client
code, not ownership of a hosted search index or a guarantee of free service.
The initial package review did not run an extension-to-Qwen comparison. The
subsequent [search evaluation](search-evaluation.md) runs representative
assignments with the same local model and different providers. Its scope and
limits are recorded separately; it is not a trial of all 15 packages.

## Main candidates

| Package and inspected version | Strengths | Costs and limitations | Fit for News |
| --- | --- | --- | --- |
| [pi-web-access](https://github.com/nicobailon/pi-web-access), 0.31.0 | Keyless Exa and several other providers; local article extraction; PDF reading; retained content for follow-up. Raw-result mode lets Qwen direct research without an extra summarizing agent. | Broad configuration and optional features we do not need. Provider selection, alternate workflows, cookies, and cloud fallbacks need explicit controls. | Leading trial candidate: useful reading coverage without operating a search server or adopting another research coordinator. |
| [pi-web-research, Wyna](https://github.com/wynainfo/pi-web-research), 1.0.1 | Readability extraction, parallel fetching, optional local browser, and cited summaries that reduce the main conversation's context. Summarizers can use the current Qwen model. | Search supports Kagi or Wyna. No suitable recurring free route was verified. Comprehensive research and normal summarized fetches add model calls; summaries can discard useful detail, although full text is available. | Eligible for comparison under the revised budget through Kagi. Extra model work and summary fidelity still need evaluation; cost alone no longer excludes it. |
| [@bcuev/pi-web-research](https://github.com/bcuev/pi-web-research), 1.0.2 | Small Brave search and local fetch extension. Timeouts, cancellation, caching, bounded output, and deterministic paragraph selection. No extra model required. | Brave only. Simpler HTML extraction and no PDF reader or browser rendering. Relevant-paragraph selection may omit context. | Strongest lightweight alternative if plain web pages cover the assignments and Brave usage stays within the selected budget. This is a different package from Wyna's. |
| [@lincoln504/pi-research](https://github.com/Lincoln504/pi-research), 1.7.0 | Full research process: plan, researchers, evaluation, further rounds, synthesis. Browser search avoids a search API subscription. Can use the current local model. | Default three parallel researchers, browser download, native components, and a separate persistent knowledge store. DuckDuckGo scraping can be blocked. More model work may contend on one Qwen instance. | Better candidate for occasional deep investigations. For daily reporting, it overlaps News orchestration and archive responsibilities. Concurrency and memory are configurable, so this is a tradeoff rather than incompatibility. |
| [pi-web-toolkit](https://github.com/Wade11s/pi-web-toolkit), 0.3.3 | SearXNG search, Scrapling extraction, batching, browser interaction, and optional free Firecrawl fallback. Useful for dynamic pages and event listings. | Needs a SearXNG endpoint plus Python/browser tooling for the full local route. Fallback can trigger on empty results as well as errors. Browser interaction exposes more actions than reading requires. | Strong option if dynamic websites prove to be the main obstacle. More services and runtimes to maintain for the initial worker. SearXNG can be an existing instance; self-hosting is not mandatory. |
| [@ollama/pi-web-search](https://docs.ollama.com/integrations/pi), 0.0.5 | Officially documented integration; two simple tools; matches the existing Ollama installation. | Hosted search still needs an Ollama account. Published code uses local experimental endpoints, fixes the host to localhost, and has no independent request timeout or output cap. It uses older Pi package names. | Worth a compatibility trial. Small enough to adapt, but not automatically production-ready because it comes from Ollama. |
| [@juicesharp/rpiv-web-tools](https://github.com/juicesharp/rpiv-mono/tree/main/packages/rpiv-web-tools), 2.11.0 | Two tools, explicit provider selection, no silent provider fallback, and several providers including Tavily. Small dependency set. | Retrieval varies by provider: Tavily fetch uses its hosted extraction API and credits; generic HTML handling is simpler than a dedicated article extractor. No keyless Exa MCP route in this release. | Good alternative if explicit routing and a documented free API quota matter more than local extraction breadth. |
| [pi-search-hub](https://github.com/ronnieops/pi-search-hub), 2.8.0 | Many providers, fallback or combined search, and keyless routes. | Combined mode can multiply requests; default page readers are hosted. The inspected Exa MCP request has a reproducible protocol failure, detailed below. | Do not choose this release for the selected Exa route without a fix and verification. This does not establish that its other providers fail. |

The Wyna package's source defaults summarizers to the current session model;
it does not require a paid model. Its built-in sourcing instructions are useful
prompts, not proof of factual accuracy. Kagi currently lists search at
$12 per 1,000 requests in its [API pricing](https://kagi.com/api/pricing).
Wyna's documentation does not establish a recurring free search allowance.

For Lincoln's package, use the scoped npm name `@lincoln504/pi-research`;
the project's README warns that unscoped `pi-research` is a different package.
Its [configuration guide](https://github.com/Lincoln504/pi-research/blob/main/docs/CONFIGURATION.md)
allows fewer researchers and disabling the knowledge store. Those changes
reduce overhead, but News would still need to control the total attempt time.

Dependency counts alone are not a quality score. The published manifests list
10 direct dependencies for `pi-web-access`, two for bcuev's extension, and
19 for Lincoln's research system. `pi-web-toolkit` lists none but calls external
Python and browser programs. Total installation and maintenance matter more
than an npm count. Pin the chosen release with Pi and Node, and test the
installed combination; advertised compatibility is insufficient.

## Other packages screened

| Package and inspected version | Useful property | Why it does not lead this selection |
| --- | --- | --- |
| [@cltec/pi-ollama-web-search](https://github.com/Cirius1792/pi-ollama-web-search), 1.0.0 | Compact output, cached full results, and selective follow-up reads help local models. | Single hosted Ollama provider. Optional file export needs restriction to worker storage. A credible alternative to the official Ollama wrapper, with compatibility and quota still to verify. |
| [pi-exa-tools](https://github.com/Tiziano-AI/pi-exa-tools), 0.3.2 | Narrow search/fetch interface with bounded output and no direct dependencies. | Requires keyed Exa, now confirmed to have a recurring free allowance. A stronger lightweight contender; relies on hosted extraction instead of local article/PDF readers. |
| [pi-exa-search](https://github.com/najibninaba/pi-exa-search), 0.1.3 | Focused discovery with date and domain filters. | Keyed Exa API; full-page extraction needs a separate tool. Its README suggests pairing it with `pi-web-access`. |
| [@feniix/pi-exa](https://github.com/feniix/pi-extensions/tree/main/packages/pi-exa), 5.1.1 | Broad Exa integration across search, contents, answers, and research. | Keyed API; answer/research capabilities add hosted work that the local-Qwen design does not need. Could expose only search and contents under Exa's free allowance, but adds broader tools and dependencies. |
| [pi-web-search](https://github.com/ttttmr/pi-web-search), 1.6.0 | Uses hosted model providers' built-in search. | Local Ollama Qwen is not a supported native-search provider. A separately selected hosted search model would add another model/service dependency. |
| [webfox](https://github.com/mavam/webfox), 4.5.0 | Explicit providers, structured CLI/library/Pi interfaces, and search plus contents tools. Can use a free provider such as Tavily. | Broader provider SDK set; hosted contents instead of a standard local article reader. Hosted answer/research features should stay disabled for this worker. Useful if News later needs the same tools outside Pi. |
| [pi-web-providers](https://github.com/mavam/pi-web-providers), 3.5.1 | Earlier version of the Webfox project. | Superseded by Webfox v4; evaluate the successor rather than start on this package name. |

## Providers and budget

The extension supplies tools; the provider supplies search results. Changing
one does not necessarily require changing the other. A free API key is allowed,
so keyless access should not outweigh reliability or a clear usage allowance.
The later budget clarification permits about $10 monthly paid search if the
results are materially better. It does not establish that a paid service wins.

| Provider | Published free access checked on September 26 | Consequence |
| --- | --- | --- |
| [Exa MCP](https://exa.ai/docs/get-started/exa-mcp) | Keyless search has free rate limits. The reviewed documentation does not give a numerical allowance. | Easy first trial. Do not assume it covers every night's load. Keyed access uses the account's plan; see the separate Starter allowance below. |
| [Exa keyed Starter](https://exa.ai/pricing) | $10 credits every month, plus an onboarding bonus; no payment method required. Standard search is $7 per 1,000 requests with up to ten results. | Roughly 1,428 standard searches per month if credits cover search alone. Extra results and content operations can consume more. Prefer evaluating this documented free allowance before paid usage. |
| [Tavily](https://docs.tavily.com/documentation/api-credits) | 1,000 credits each month, no credit card. Basic search uses one credit; advanced search uses two. | Best documented free API alternative in this review. Keep pay-as-you-go disabled for the free baseline. Roughly 33 basic searches per day on a 30-day average, shared across all reporters and retries; hosted extraction also consumes credits. |
| [Brave](https://brave.com/search/api/) | $5 monthly credits; search costs $5 per 1,000 requests. | Approximately 1,000 plain search requests each month. Enforce the selected spending limit before unattended use. Do not rely on older package claims of 2,000 free requests. |
| [Ollama](https://ollama.com/blog/web-search) | Search is included for free accounts, with higher limits on paid plans. | Another reasonable free trial. The reviewed documentation does not establish a numeric free quota. Local Ollama inference does not make the search service local. |
| [Firecrawl keyless](https://www.firecrawl.dev/blog/firecrawl-keyless-launch) | 1,000 credits every month without an API key or signup. | Makes toolkit's optional hosted fallback more viable than the initial review recognized. Credits must cover the selected search, scrape, or interaction operations. |
| [SearXNG](https://docs.searxng.org/) or direct search-page scraping | Open software can query upstream engines without a paid API. | More control, with instance maintenance, upstream limits, and page or bot-blocking changes. Free software does not ensure continuous access. |

The initial review had not established Exa's recurring keyed allowance from
its MCP documentation. Checking the pricing page corrected that gap. This
makes the small keyed Exa adapters eligible even for a free baseline.

Kagi also becomes eligible under the conditional paid budget. At its published
$12 per 1,000 searches, $10 covers about 833 searches before other charges.
That is a capacity estimate, not evidence of better results. Compare its
sources with Exa and the other free candidates on the same assignments.
Paying for higher limits alone does not demonstrate superior relevance.

## Concrete protocol check

The published `pi-web-access` 0.31.0
[Exa implementation](https://github.com/nicobailon/pi-web-access/blob/610a52033f1e9705c0023ff9e0fac399319310a3/exa.ts)
and `pi-search-hub` 2.8.0
[Exa implementation](https://github.com/ronnieops/pi-search-hub/blob/96ccf692123d35a3cf4b615d597a80fe9e9f6229/extensions/backends/exa-mcp.ts)
construct different requests. Reproduced each request with Node's `fetch` on
this Mac, without credentials, using the same public documentation query.

- The web-access request returned HTTP 200 with a source URL and content.
- The search-hub request returned HTTP 406 because its headers do not accept
  both JSON and the event-stream response format. Its code also places the
  tool name inside the arguments object and attempts JSON-only parsing;
  those further issues were observed in source, not separately verified live.

An initial Python HTTP probe was rejected with HTTP 403 for its client
signature. The Node request that matches the selected extension then worked.
This demonstrates why the actual client matters. It does not establish
long-term availability, quota, extension compatibility, or Qwen report quality.
No package was installed in the owner's Pi environment for this check.

## Recommendation and conditions for changing it

Keep `pi-web-access` as the leading implementation trial. The deciding benefit
is its local reading support across articles and PDFs, coupled with free search
and no required secondary research agent. News can retain control of reporting
instructions, archive context, retries, and delivery.

Its main disadvantage is the amount of optional behavior to constrain.
Implement explicit provider and workflow restrictions in the worker integration,
use raw results, and expose only needed tools. Verify these controls rather than
assuming configuration alone enforces them. Do not inherit personal credentials.
This is the tradeoff for reusing extraction code instead of maintaining it in News.

The initial accepted route was keyless Exa. With the confirmed Starter
allowance, recommend evaluating keyed Exa for the first trial. Compare Tavily
and other free routes on the same assignments. Include Kagi or paid Exa usage
if it can demonstrate a material gain within the conditional budget. These
are evaluation recommendations, not newly enabled automatic fallbacks.

Choose bcuev's smaller extension if its simpler reading tools produce equally
good reports on representative assignments and Brave usage fits the selected
budget. The small keyed Exa adapters also merit evaluation now that their
provider has a confirmed recurring free allowance. Choose toolkit if browser-dependent sources dominate.
Choose Lincoln's research system if deeper investigations show a measured
benefit from its extra model work. An Ollama wrapper is also worth comparing
if minimal setup and small code size become the stronger requirements.

The next implementation evaluation should compare actual cited reports,
omitted source details, request counts, blocked pages, and total runtime on
the same assignments. Include an article, a PDF, and a dynamic event page.
Test cancellation and quotas within the existing attempt limit. Do not treat
this package survey or the successful HTTP request as that evaluation.

The owner subsequently requested concrete test prompts and provider runs.
See the [search service evaluation](search-evaluation.md) for those inputs,
controls, and findings.
