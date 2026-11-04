# Candidate Triage (Phase 3)

Date: 2026-11-02. Sources: Hugging Face model cards and config.json (VERIFIED), llama.cpp upstream git log (VERIFIED), vendor benchmark tables (VERIFIED as published, NOT independently reproduced). Memory figures are ESTIMATED from configs until measured.

## Hard size ceiling (ESTIMATED)

Usable memory ≈ 24 GB VRAM + ~95 GB RAM (125 GB minus OS/services ~21 GB, minus headroom). Weights that must be resident therefore need to stay under ~100 GB. At 3–4.5 bits per weight this caps total transformer parameters at roughly 170–250B. Anything ≥ 400B is class D.

Exception that matters: Qwen3.8-Flash-Next's 51B n-gram embedding is a lookup table. llama.cpp mmaps it, so only the rows used are paged in from NVMe. It does not need to be resident.

## Finalists (ADVANCE)

| # | Model | Why | Hardware class | First blocker to check |
|---|---|---|---|---|
| 1 | **Qwen3.8-Flash-Next** (125B + 51B n-gram, 6B active) | Best vendor coding/agent scores of anything that fits (SWE-bench Pro 62.5, LiveCodeBench v6 91.9, GPQA 91.7). Hybrid GDN + Qwen Sparse Attention: only 12 layers keep KV, 2 KV heads → ~6.4 GB at 256K. | B (GPU + RAM offload) | New arch (qwen4exp) needs llama.cpp from Oct 2026; QSA quality under quantization unknown |
| 2 | **Nemotron 3.5 Super VL 120B-A12B** | Native 1M context; 9 attention layers × 2 KV heads → ~2.4 GB KV at 256K, ~9.4 GB at 1M. Best candidate for the 512K/1M extension. | B | Mamba2 prefill speed with CPU-resident experts |
| 3 | **Nemotron 3.5 Bolt 74B-A9B 24GB** | Quantization-aware 2-bit, built to fit 24 GB. Vendor table beats Qwen3.6-35B on Terminal-Bench, HLE, GPQA, AA-LCR (64.1). | A (mostly GPU) | 2-bit QAT quality on long reasoning |
| 4 | **Qwen3.8-27B** (dense) | Already downloaded (NVFP4 + INT4). Dense reasoning baseline, SWE-bench Pro 61.7. | A/B | KV 16.8 GB bf16 at 256K → needs q8 KV or KV offload |

## Held (eligible, tested only if finalists fail)

Ling-3.0-flash (124B-A5B, KDA+MLA, 256K) · Qwen3.6-35B-A3B (control) · Qwen3-Coder-Next · Gemma 4 31B / 26B-A4B · MiniMax-M3.1-Flash (220B, KV too large).

## Experiment (limited proof of concept only)

GLM-5.3-Flash (321B, KDA + DeepSeek sparse attention, 1M native). Only fits near 2.5 bpw (~100 GB). Worth one load test if budget remains after finalists.

## Rejected

- Context below 256K: gpt-oss-120b (131K).
- Too large for this workstation (class D): DeepSeek V4.x, Kimi K2.6/K3, MiniMax-M3, GLM-5.2/5.3, Muse Spark Open 816B, Mistral Large 4, Nemotron 3 Ultra, Ling-3.1-flash, Qwen3.8-2.4T.
- Dense with huge KV: Mistral Medium 3.5 128B.
- Superseded: Kimi-Linear-48B.
- HyGA (Hybrid Gated Attention): research only — see architecture-research.md.

## Outstanding questions

1. Does llama.cpp's QSA implementation match the reference at 256K (sparse block selection is new code)?
2. Mamba2 / GDN prefill throughput at 256K with experts in RAM — estimate hours or minutes?
3. Bolt's 2-bit QAT: does long-context reasoning hold up versus Super at 4-bit?
4. Vendor benchmarks are self-reported. Independent long-context evidence (RULER, AA-LCR) is only available for Bolt.
