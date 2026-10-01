# Evaluation reports

Saved model drafts from the September 2026 reporting and writing pilots. These are
experimental outputs with known errors, not published recommendations.
Read the [Pi/Qwen prompts and source checks](../search-evaluation.md) and
[Codex comparison](../worker-codex-evaluation.md) before using any details.

## September 26 reporting pilot

| Assignment | Pi/Qwen + Exa keyless | Pi/Qwen + Firecrawl keyless | Codex + GPT-6 Luna |
| --- | --- | --- | --- |
| AI model brief | [Exa draft](ai-exa.md) | [Firecrawl draft](ai-firecrawl.md) | [Luna draft](ai-codex-luna.md) |
| Family activities | [Exa draft](family-exa.md) | [Firecrawl draft](family-firecrawl.md) | [Luna draft](family-codex-luna.md) |

Model text is preserved unchanged. Tool transcripts, raw source content,
installation files, and one-off experiment scripts remain in the active
checkout's ignored `.cache/search-pilot/` directory. That directory is not
required to read the prompts, reports, or findings committed here.

## September 30 writing comparison

Read the [Sleep and fitness writing comparison](../worker-writing-evaluation.md)
for the method, factual problems, timing limits, and link to the accepted
decision. The local-model drafts contain known errors and remain unchanged.

- Inputs: [original reporter assignment](sleep-fitness-reporter-prompt.txt) and
  [identical writing prompt with research](sleep-fitness-writing-prompt.txt).
- Drafts: [Sol high](sleep-fitness-sol.txt), [Qwen xhigh](sleep-fitness-qwen.txt),
  and [Hemmingway with thinking off](sleep-fitness-hemmingway.txt).
- [Run measurements](sleep-fitness-writing-runs.json), including the earlier
  Qwen timeout and Hemmingway's unsuccessful thinking-enabled attempt.

These files preserve the September 30 evidence without depending on the
ignored local HTML preview, logs, or production-database snapshot.
