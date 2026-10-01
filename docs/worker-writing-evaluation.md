---
status: current
---

# Sleep and fitness writing comparison

This private test on September 30, 2026 compared GPT-6.1 Sol, local Qwen,
and local Hemmingway as writers using the same completed research. After
reading the drafts, the owner chose to [retain the current Sol approach](reporting-worker.md#model-engine).
This records one writing experiment, not a general model ranking or a full
reporting-worker evaluation. No test article was submitted to the newsroom.

## Assignment and shared inputs

The test used the Sleep & Fitness reporter scheduled for October 1. Research
was completed the previous evening in Pacific Time, covering September 24–30.
It was an early rehearsal, not the reporter's scheduled production run.
A read-only history check found no earlier runs for this reporter and no
duplicate coverage among the twelve retained newsroom articles.

The supervising agent researched two new trials: pressure-airway treatment
after stroke and exercise scheduled at an older adult's measured peak or
trough strength time. All three writers received the same evidence. The exercise paper was read in
full; the stroke paper was available only as its primary abstract.

The [original reporter assignment](evaluations/sleep-fitness-reporter-prompt.txt)
required research. The [shared writing prompt](evaluations/sleep-fitness-writing-prompt.txt)
instead assigned writing only, prohibited additional tools and facts from
memory, and included the captured newsroom guidance beginning “Write for an
intelligent, curious reader.” Its background-verification instruction was
adapted to the supplied evidence. Later changes to the production wrapper
were not substituted into this test.

The test added an approximate 350–450-word target and a maximum of 90 words
derived from each new study, including the title and summary. These were test
constraints, not production reporter requirements. Each writer was asked for
a headline, one-sentence summary, connected prose, and inline source links.
The complete user prompts matched byte for byte. Their SHA-256 hash was
`646016b3fc35a16fedcd0ef49999067c7efa76573b3e5b632916ec4a11b93bc7`.

## Configuration and measured results

Sol ran through an isolated Codex CLI invocation using the existing ChatGPT
authentication. Web search, shell tools, personal configuration, project
instructions, connectors, and subagents were disabled. Its event log recorded
no writer tool calls. The local models ran directly through Ollama 0.34.4,
without Codex or Pi. Local runs were sequential to avoid GPU contention.

| Writer | Reasoning setting | Completed run | Words | Preserved draft |
| --- | --- | --- | --- | --- |
| `gpt-6.1-sol` | High | 60.41 seconds | 412 | [Sol](evaluations/sleep-fitness-sol.txt) |
| `qwen3.8:27b-mlx` | xhigh | 797.02 seconds, or 13m 17s | 382 | [Qwen](evaluations/sleep-fitness-qwen.txt) |
| `hemmingway:27b-q6` | Thinking off | 90.03 seconds, or 1m 30s | 509 | [Hemmingway](evaluations/sleep-fitness-hemmingway.txt) |

Elapsed time includes model loading, prompt processing, reasoning, and writing;
it excludes shared research. Word counts use visible article text, including
headings and summaries, without Markdown syntax or link URLs. The
[saved measurements](evaluations/sleep-fitness-writing-runs.json) retain the
completed runs and unsuccessful attempts.

The installed Qwen model supported low, medium, and xhigh reasoning, with no
high option. The test used xhigh after the owner requested high. An initial
xhigh attempt stopped at the test runner's 600-second limit without an article.
Its successful retry reused a loaded model and cached prompt. Final article
text began at 779.53 seconds; completion followed about 17.5 seconds later.
The run generated 24,493 tokens including reasoning.

Hemmingway's first run requested thinking, with xhigh as its template default.
It repeatedly revised and counted words, then reached the 1,800-second limit
without a final article. Its reasoning arrived in Ollama's main response field;
that output was not treated as article prose. The separately labeled retry
used thinking off and the identical user prompt. Its 90.03-second result
excludes the failed 30-minute attempt. The production worker's configured
attempt limit was also 1,800 seconds.

An earlier medium-reasoning trial was superseded when the owner clarified the
settings and writing-only prompt. Its output was not used in the comparison.

## Factual review

The review checked each draft against the shared packet, with focused source
checks where needed. Review findings were not sent back to any writer, and
the saved drafts were not corrected.

Sol retained the uncertain main heart result and the secondary status of the
recovery finding. Its numbers and source links matched the packet. One
precision issue remained: it called the exercise study's limb lean-mass
measurement “limb muscle mass.”

Qwen described main measurements as unchanged, which confuses a lack of clear
differences between groups with a lack of change within participants. It also
removed the qualification that the exercise study reported no serious events
*related to the intervention*. Its account of the older timing review was
internally confusing. A blood-biomarker claim was absent from the supplied
results and needed a clearer comparison: the
[stroke abstract](https://pubmed.ncbi.nlm.nih.gov/42786612/) reports a decrease
within the CPAP group without a difference between groups.

Hemmingway called the stroke trial Swiss-based. Its
[registered site](https://clinicaltrials.gov/study/NCT04458779) was in Taiwan;
the exercise trial was Swiss. The same registry lists a masked outcome
assessor, so the draft's blanket description of an unblinded analysis needed
qualification. It also substituted low energy for measured low strength,
overstated the timing result as adding nothing, and garbled the treatment-arm
description. It exceeded both the approximate length target and the brief
per-study limits.

The [exercise paper](https://onlinelibrary.wiley.com/doi/10.1002/jcsm.70390)
and the sources in the shared prompt support the review. These experimental
drafts are evidence for this comparison, not published health guidance.

## Interpretation and evidence retention

The owner found the Sol draft acceptable and retained the existing approach.
The [worker design](reporting-worker.md#model-engine) is the authoritative
decision record. This test did not change production models, reasoning,
reporter schedules, or the division of research and writing.

One assignment and one completed draft per configuration cannot establish
general quality or latency. Platform instructions, model formats, sampling
defaults, and reasoning controls differed. Hemmingway's completed run used
thinking off; Sol's high and Qwen's xhigh are not equal reasoning budgets.
The strict test word limits also affected behavior: Hemmingway spent much of
its unsuccessful attempt repeatedly counting and revising text. These times
should not be generalized to unconstrained writing or complete newsroom runs.

The linked inputs, raw drafts, and measurements are retained with this report.
The optional HTML comparison, full local logs, and superseded attempts remain
under the checkout's ignored `var/comparisons/2026-09-30-sleep-fitness/` directory.
That directory is not needed to read the preserved study. The production
database snapshot, runtime credentials, and private invocation paths are not
part of the documentation archive.
