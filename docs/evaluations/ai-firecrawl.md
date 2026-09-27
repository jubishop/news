---
status: draft
---

> Evaluation artifact: firecrawl keyless search, local Qwen, September 26, 2026.
> Unedited model draft with known errors. See the [source checks](../search-evaluation.md#pilot-findings).

# Weekly AI Model Brief — Sep 20–26, 2026

Three releases this week matter for individual developers. All were announced **and are already live** as of the cutoff. Vendor-reported benchmark numbers are flagged where they are not independently verified.

## 1. Anthropic — Claude Opus 5.5 (Sep 22, 2026)
**What changed:** New flagship in the Claude 5.5 family. Anthropic positions it as comparable to Fable 5.1 on most work at ~40% lower cost than Opus 5, with output >30% faster and stronger prompt-injection resistance. Pricing fell to **$4/$20 per M (input/output)** from $5/$25, and cache reads to **$0.20/M** (60% less) — the vendor credits the cache drop for most of the savings on agentic/coding work. It leads Anthropic's published benchmarks on agentic coding and knowledge work.
**Available now:** Yes, via the Claude API; fast mode (up to 2.5x, $8/$40) in Claude Code and the Claude Platform.
**Limitation:** API-only, **not open weights**. Because it matches Mythos 5.1 in biology/cybersecurity, those dual-use capabilities are gated behind the Life Sciences and Cyber Verification Programs — unverified developers get the safeguards, not full access. All performance/cost figures are Anthropic's own tests; **Reuters independently confirms the launch date and the 40% price cut, but not the benchmark margins.**
Sources: [Anthropic](https://www.anthropic.com/claude-opus-5-5) · [Reuters](https://www.reuters.com/business/anthropic-unveils-claude-opus-55-2026-09-22/)

## 2. xAI — Grok 4.7 (Sep 21, 2026)
**What changed:** New frontier model for coding/knowledge work, trained on a larger base with a longer RL run weighted toward multi-hour tasks; better self-verification and long-context handling. Same price as Grok 4.6 (**$2/$6 per M**); a 2x-speed fast variant also exists. A third-party tracker reports a ~500k-token context.
**Available now:** Yes — xAI API as `grok-4.7`, plus Cursor and Grok Build.
**Limitation:** **Closed weights.** The public API serves the base model only; the "fast" (2x) variant is restricted to Cursor/Grok Build. Benchmarks (e.g., CursorBench 4.0 46.3%, Top on HackerBench v0.3) are **xAI-reported and not independently verified**.
Sources: [xAI news](https://x.ai/news/grok-4-7) · [xAI release notes](https://docs.x.ai/developers/release-notes)

## 3. Alibaba Qwen — Qwen-Image-2.1 (Sep 21, 2026)
**What changed:** Open-weight **7B diffusion model unifying text-to-image and editing** (up to 10 reference images, local edits, native RGBA transparency, 2K output) in a single checkpoint — down from the 20B original's separate generation/editing setup. Day-0 support for Diffusers, ComfyUI, vLLM-Omni, SGLang; AMD ROCm and FlagOS coverage too. Includes two Qwen3.5-VL prompt-rewriter checkpoints.
**Available now:** Yes — weights on Hugging Face, runnable locally (CPU offload eases memory on smaller GPUs).
**Limitation:** The 7B figure covers **only the DiT** — the pipeline also loads an 8B Qwen3-VL encoder, so real VRAM needs exceed the headline number. It tops the open-weight column on **Qwen's own in-house benchmark only**, and the **Qwen Research License bars commercial use** without a separate agreement.
Sources: [Qwen/Qwen-Image-2.1 (HF)](https://huggingface.co/Qwen/Qwen-Image-2.1) · [MarkTechPost summary](https://www.marktechpost.com/2026/09/21/alibaba-qwen-releases-qwen-image-2-1/)

---
*Note:* OpenAI's "GPT-6 Sol/Luna" and a "Better prompt caching for GPT-6" update (~Sep 22) also surfaced this week, but OpenAI's domain returned HTTP 403 to the fetch tools, so these are omitted pending a verifiable primary source rather than relied on via secondary reporting.
