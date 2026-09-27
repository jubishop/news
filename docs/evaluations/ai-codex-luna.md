---
status: draft
---

# Codex Luna AI model brief

> Evaluation artifact: Codex GPT-6 Luna with built-in web tools, September 26, 2026.
> Unedited model draft with known limitations. See the [source review](../worker-codex-evaluation.md#source-review).

## Weekly AI model brief: Sep 20–26, 2026

Two verified releases or substantial updates stood out for individual developers. The performance figures below are vendor-reported unless noted otherwise.

- **Sep 22 — OpenAI GPT-6 Sol and GPT-6 Luna.** OpenAI added two text-and-image reasoning models to its Responses and Chat Completions APIs. Published prices per million tokens are $2 input/$10 output for Sol and $0.10/$0.50 for Luna (with lower cached-input rates). **Available now:** Yes, through the API. **Limitation:** They return text, not generated images; listed standard prices cover prompts up to 272K input tokens, with other pricing for longer prompts and processing tiers. [OpenAI API changelog](https://developers.openai.com/api/docs/changelog)

- **Sep 22 — Anthropic Claude Opus 5.5.** Anthropic says the new model matches Fable 5.1 on most work, with 40% lower cost on typical workloads than Opus 5. It is positioned for coding and longer agent tasks; API list prices are $4 per million input tokens and $20 per million output tokens. **Available now:** Yes, through Claude products and the Claude Platform. **Limitation:** Cybersecurity work beyond routine software development is generally routed to Opus 4.8; broader access for verified cyber practitioners is planned. Anthropic’s benchmark and cost claims are company-reported, though its announcement also describes outside pre-release evaluation. [Anthropic announcement](https://www.anthropic.com/claude-opus-5-5)

- **Sep 25 — OpenAI vision-encoding fix for GPT-6 Sol and Luna.** OpenAI says it fixed an image-encoding bug that degraded image understanding, improving visual tasks in the API and Codex, including computer use. **Available now:** The changelog records the fix as complete. **Limitation:** The announcement provides no independent evaluation or quantified improvement; developers with image-input workflows should rerun their own evaluations. [OpenAI API changelog](https://developers.openai.com/api/docs/changelog)

I found no verified local or open-weight model release in the reviewed sources for this week, so I have not included one.
