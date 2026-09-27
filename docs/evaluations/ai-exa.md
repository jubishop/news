---
status: draft
---

> Evaluation artifact: exa keyless search, local Qwen, September 26, 2026.
> Unedited model draft with known errors. See the [source checks](../search-evaluation.md#pilot-findings).

# AI Model Brief — September 20–26, 2026

Three model releases/updates landed this window, all targeting coding or content work and all live to API users. No new general open-weights release was confirmed for these seven days.

## 1. OpenAI — GPT-6 Sol and Luna (Sep 22, 2026)
OpenAI expanded the GPT-6 family with two smaller, cheaper siblings of flagship GPT-6 Astra, placed down the cost–intelligence curve. OpenAI says it cut Sol and Luna API prices 50% versus the GPT-5.6 promotional rates, attributing savings to caching/inference gains, and that both inherit Astra's methods for "professional work, factuality, coding, computer use, and alignment."
- **What changed:** two new API models, `gpt-6-sol` and `gpt-6-luna`.
- **Available now:** Yes — in ChatGPT Work and Codex (Plus/Pro/Business/Enterprise/Edu) and the OpenAI API; Luna is also in the desktop app for Free/Go users.
- **Practical limitation (dev):** Not yet in the standard ChatGPT "Chat" interface; Sol requires a paid tier and rollout in ChatGPT was gradual.
- **Verification:** OpenAI's price/capability claims are vendor-published; independent corroboration is GitHub adding both models to Copilot this same week.

## 2. xAI — Grok 4.7 (Sep 21, 2026)
xAI's new frontier model for coding and "knowledge work," built on a larger base than Grok 4.6 with a longer reinforcement-learning run weighted toward multi-hour tasks, natively trained on the Grok Bot harness, with a new safeguard stack.
- **What changed:** larger base, an xHigh reasoning tier, plus new cyber/biosafety mitigations. xAI claims it tops its own CursorBench 4.0 (46.3% vs 40.4% for 4.6) and 62.4% on LatchBio's biosafety benchmark.
- **Available now:** Yes — in Cursor and "Grok Build," and via the Grok API. Unchanged pricing vs 4.6: $2/M input, $6/M output.
- **Practical limitation:** The headline "twice as fast, half the price" is relative to Fable 5.1 / GPT-5.6 Sol, not to Grok 4.6 (which costs the same); a "fast" variant costs 2× ($4/$12). Red-team/cyber access is invite-only, and the benchmark table is xAI's own (CursorBench 4.0), not an independent eval.
- **Verification:** Independently confirmed live in GitHub Copilot this week.

## 3. Google — Gemini 3.8 Flash TTS and Flash-Lite TTS (Sep 22, 2026)
Per Google's Gemini API release notes, two next-gen text-to-speech audio models reached general availability, alongside a new `/v1beta/voices` endpoint.
- **What changed:** `gemini-3.8-flash-tts` (flagship "studio-grade" fidelity, dialects, long-form multi-turn stability) and `gemini-3.8-flash-lite-tts` (fast, low-cost, built to replace `gemini-3.1-flash-tts-preview`), with new voice design, voice replication, and a 150+ voice library.
- **Available now:** Yes, via the Gemini API.
- **Practical limitation:** Voice replication requires consent verification, and Flash-Lite TTS is a drop-in replacement for a preview model — a migration for existing voice-agent chains, not a free upgrade.

---

**Sources (original announcements / release notes):**
- OpenAI, *Introducing GPT-6 Sol and Luna* (Sep 22): https://openai.com/index/introducing-gpt-6-sol-and-luna/
- xAI, *Introducing Grok 4.7* (Sep 21): https://x.ai/news/grok-4-7
- GitHub, *Copilot weekly releases — September 21* (changelog dated Sep 25, independently confirms Sol, Luna, and Grok 4.7 live in Copilot): https://github.blog/changelog/2026-09-25-github-copilot-weekly-releases-september-21/
- Google, *Gemini API release notes* (TTS GA, Sep 22): https://ai.google.dev/gemini-api/docs/changelog

**Method note:** GPT-6 Sol/Luna and Grok 4.7 are corroborated by two independent outlets (each vendor's own page plus GitHub's Copilot changelog); Gemini TTS is confirmed from Google's official changelog. OpenAI's page returned HTTP 403 to direct fetch, so its claims were read via the search index quote and cross-checked against GitHub's independent changelog. All three are confirmed live. Other activity in-window (e.g., Gemini 3.8 Live "Live Avatar," enterprise-only) was excluded as less useful to an individual developer. No new general open-weights model was verifiable for Sep 20–26.
