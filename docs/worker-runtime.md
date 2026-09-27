---
status: draft
---

# Local reporting worker runtime

This is the September 26, 2026 research and implementation proposal for the
external News worker. The [worker boundary](reporting-worker.md) remains the
behavior reference; the [server contract](server-contract.md) defines the
implemented API. This is a design record. Worker installation and end-to-end
research evaluation remain implementation work.

## Decision state

The [model decision](reporting-worker.md#model-engine) selects the installed
Qwen 27B model through Ollama. The exact local tag is `qwen3.8:27b-mlx`.
The [host decision](reporting-worker.md#worker-location) selects the current
Mac, with [daily startup](reporting-worker.md#daily-work-discovery) at 03:00
Pacific Time. This is a simple daily schedule, with no new morning deadline
or strict past-night coverage cutoff.

The [research integration decision](worker-web-research.md#selected-integration-and-alternatives)
selects Pi with `pi-web-access` and free Exa search after research into
alternatives. The surrounding supervisor design remains a recommendation.
The [free-service requirement](worker-web-research.md#accepted-cost-and-ownership-constraint)
applies to the whole integration.

## Local observations

Read-only inspection on September 26, 2026 found:

| Item | Observation |
| --- | --- |
| Hardware | Apple M5 Pro, 64 GiB unified memory. |
| Operating system | macOS 27.0. |
| Ollama | 0.34.4. |
| Selected model | `qwen3.8:27b-mlx`, local ID prefix `5642e97495e1`, about 18 GB on disk. |
| Model metadata | 27.8B parameters, `nvfp4` quantization, 262,144-token advertised context. |
| Reported capabilities | Completion, vision, tools, and thinking. |
| Pi | 0.87.1, managed installation of `@earendil-works/pi-coding-agent`. |
| Existing Pi model | Local Ollama `/v1` endpoint using `openai-completions`; Qwen is already the default. |
| Existing Pi extensions | No research extension was configured; one terminal-tab extension was present. |
| Power configuration | AC idle sleep was disabled; no timed wake schedule was listed. |

These are observations, not a supported-version policy. Pin the worker's Pi,
extension, and Node versions together when implemented. Do not make unattended
News behavior depend on changes to the owner's interactive Pi defaults.
Record the resolved model digest locally for evaluations and deliberate model
updates; keep the accepted newsroom schema free of model fields.

### Local tool-use probe

One isolated probe ran Pi 0.87.1 against the installed Qwen model with medium
thinking. It used a temporary agent directory, no personal extensions or
context files, no built-in coding tools, no saved session, and only two test
tools. No web service or newsroom endpoint was called.

The first tool returned a fictional bulletin with a source URL, a date, a
single fact, and a verification code that the prompt did not contain. The
second tool accepted report fields only if the source URL and verification
code matched the first result. Pi executed both tools successfully, consumed
their results, and ended normally. Elapsed wall time was 17.02 seconds.

This establishes a basic two-tool round trip through the installed harness
and model. It does not test web retrieval, article-schema compliance,
long-context reliability, factual judgment, a full assignment, or concurrent
load. Do not extrapolate a daily capacity from this short probe.

## Recommended execution boundary

Recommendation: use a small Python supervisor and a dedicated Pi subprocess
for each research attempt. Keep the server and worker protocol in Python,
consistent with the repository. Let Pi manage the model conversation and
research tool loop.

| Approach | Benefit | Cost and recommendation |
| --- | --- | --- |
| Python supervisor plus Pi subprocess | Reuses the working local model setup, agent loop, tool handling, and context management. | Adds a pinned Node/Pi runtime and a small News extension. Preferred first evaluation. |
| Python directly calling Ollama | One application language, direct control of tool calls and structured output. | News owns the conversation loop, tool dispatch, context limits, and model-specific recovery. Fallback if Pi adds more maintenance than it removes. |
| TypeScript worker using Pi SDK | Direct control of sessions and custom tools without a subprocess protocol. | Adds a second application language for durable worker operations already suited to Python. Consider only if subprocess control becomes awkward. |

Pi documents [scripted CLI modes](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli-integration.md)
and [SDK integration](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md).
Its [model configuration](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md)
supports Ollama through a compatible endpoint. Start with a one-attempt JSON
event stream, not a persistent general-purpose agent service. JSON mode
reports events; it does not enforce an article schema. Inspect the final
model stop reason and settled state, not merely process exit code or the
first end event. A failed assistant response can still leave JSON mode with
exit status zero.

The supervisor should own deterministic operations:

1. Acquire a process lock and recover the durable local journal.
2. Retry delivery of completed results before replacing unfinished attempts.
3. Check in, obtain due runs, and claim only work it is ready to process.
4. Handle pause acknowledgments without invoking the model.
5. Supply the exact claimed instructions, dates, and relevant archive context.
6. Start one isolated research process; renew claims and enforce resource limits.
7. Validate and durably save the complete candidate result before submission.
8. Retry identical submissions until acknowledged, retaining request IDs and
   receipts as required by the server contract.

Use one research attempt at a time initially. Keep Qwen loaded while processing
the batch. Measure throughput and memory before adding parallel model calls.
The server allows three research attempts, a 15-minute delay after retryable
reported failures, and explicit replacement of abandoned attempts. Do not
multiply that allowance with independent unbounded retries in the harness.
Communication retries must reuse the saved operation; they are not new research.

Give Pi only web discovery, source reading, archive search/read, and a typed
candidate-result tool. The candidate-result tool does not publish. Keep News
publication credentials in the supervisor and mediate archive access. Load
only reviewed extensions in a worker-specific agent directory and working
directory. Do not expose general shell or file-editing tools to reporting.
This limits the effects of untrusted instructions embedded in retrieved pages;
a prompt alone is not that boundary. Extensions themselves remain trusted code.

## Research tools

The [web research proposal](worker-web-research.md) records the accepted
free-service requirement and compares search alternatives. The selected
initial route uses the extension's free, keyless Exa search and local page
extraction.
Qwen does the reasoning and writing. A separate search server is unnecessary
for the first evaluation.

Use `nicobailon/pi-web-access` as the Pi integration for search, page
reading, and PDFs. Its existing extraction support can avoid maintaining these
parsers in News. Use a pinned release with only approved providers and the
raw-result workflow. The extension itself has not been installed or tested.

A search result is a discovery lead, not sufficient evidence for publication.
Read the relevant source pages, record URLs and retrieval times, and distinguish
publication dates from event dates. Treat blocked pages, missing details, and
conflicting sources explicitly. Search failure cannot become a successful
"nothing to publish" outcome.

## Daily startup

The accepted schedule is 03:00 Pacific each day. Recommendation: use macOS
`launchd` as the platform's daily cron equivalent. Keep the job definition
small, with explicit executable and working-directory paths. Use
`America/Los_Angeles` for worker calendar calculations and configure the
schedule consistently with the Mac's timezone.

Apple documents that a [calendar job missed during sleep](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html)
runs on wake; a job missed while powered off is not automatically replayed by
that schedule. A per-user job also needs a logged-in user. Keep ordinary startup
recovery and a process lock so restarts or manual starts do not duplicate work.
Use the existing server catch-up and failure behavior when the Mac is unavailable.
The inspected Mac already has AC idle sleep disabled.

The owner's past-night and wake-time remarks do not add a research date limit,
completion deadline, earlier alert, or benchmark requirement. Coverage remains
controlled by each assignment and its history, including future-facing reports.
The server's existing full-day lateness rule remains unchanged.

## Evaluation before unattended publication

Use the reference assignments with public or synthetic configuration first.
Keep their draft outputs local during evaluation. The production server
publishes an accepted article result immediately; it is not a draft inbox.

- Prove the exact installed model and pinned extension can search, read pages,
  retrieve archive context, and produce a complete server-valid candidate.
- Review citations, source support, publication/event dates, duplicate handling,
  unsupported claims, and honest treatment of unavailable details.
- Run a prior-day news report, a missed-week catch-up, the future-weekend
  shortlist, and a quiet assignment with a valid empty result.
- Test outages, blocked sources, malformed model output, tool errors, and a
  hostile page. Verify they cannot trigger arbitrary tools or false success.
- Exercise crash recovery, lost claim responses, lost submission acknowledgments,
  pause, deletion during research, exhausted attempts, and duplicate starts.
- Verify actual context allocation and memory use on a representative assignment;
  advertised context alone does not establish a working configuration.

Ollama supports [tool calling](https://docs.ollama.com/capabilities/tool-calling)
and [schema-constrained output](https://docs.ollama.com/capabilities/structured-outputs).
That supports the direct-API alternative but does not imply Pi enforces a
final article schema. Its [context guidance](https://docs.ollama.com/context-length)
explains that larger context requires more memory. Evaluate a bounded context
with the exact endpoint configuration and verify it with `ollama ps`; do not
assume Pi's declared context changes Ollama's allocation.

## Open decisions

Resolve these through the design interview, one question at a time:

- Bounds for a stuck research attempt, minimum publication evidence, and
  behavior when a requested report cannot be supported fully.
- Archive context limits and local log/result retention.

Accepted answers belong in their authoritative sections with their reasons;
unanswered questions remain proposals. Implementation work should be tracked
in GitHub Issues after the required behavior is settled.
