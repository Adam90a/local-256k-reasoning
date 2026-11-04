# Long-Context Architecture Research (Track B)

Date 2026-11-02. Evidence labels per brief §17.

## Bottom line

On a 24 GB GPU, context memory is decided by **how many layers keep a full KV cache and how many KV heads they have** — not by advertised context. Every 2026 model that is both strong and fits this machine is a **hybrid**: most layers use a fixed-size recurrent state (Gated DeltaNet, Kimi Delta Attention, or Mamba-2), and a minority keep a KV cache, often with sparse/top-k attention on top. The result is 256K of context costing 2–7 GB instead of 50–100 GB. (VERIFIED from configs; memory ESTIMATED.)

## Families evaluated

| Family | Memory vs context | Compute vs context | Long-range retrieval | Weights that fit here | Maturity |
|---|---|---|---|---|---|
| Dense full attention (GQA) | linear, large (Mistral Medium 3.5: ~360 KB/token) | quadratic | best in principle | none at 256K | production |
| Sliding window + periodic global (Gemma 4) | linear in global layers only | mostly linear | weaker beyond window; relies on global layers | Gemma 4 31B / 26B-A4B | production |
| Gated DeltaNet 3:1 + gated attention (Qwen3.5/3.6/3.8-27B) | 1/4 of layers keep KV | linear + 1/4 quadratic | good (vendor), RULER-type evidence UNKNOWN | Qwen3.8-27B, Qwen3.6-35B | production |
| Gated DeltaNet 3:1 + **Qwen Sparse Attention** (Qwen3.8-Flash-Next) | 12 KV layers × 2 heads ≈ 24.6 KB/token | linear + sparse (2,048-token budget per query via a block indexer) | UNKNOWN — new mechanism, must be measured | yes (Q4 ≈ 82 GB + n-gram table on disk) | new (Aug 2026), "experimental preview of Qwen4 architecture" |
| Mamba-2 + few attention layers (Nemotron 3.5 Super/Bolt) | 9 attention layers × 2 KV heads ≈ 9.2 KB/token | ~linear | Bolt AA-LCR 64.1 (vendor); Super trained to 1M | yes (Super NVFP4 77 GB; Bolt 22 GB) | production |
| KDA linear + MLA (Kimi Linear, Ling-3.0) | MLA latent 576/token on 1-in-6 or 1-in-4 layers | linear + small quadratic | Kimi Linear published 1M results | Ling-3.0-flash (HOLD) | production |
| KDA + DeepSeek sparse attention (GLM-5.3-Flash) | MLA + sparse | linear + sparse | UNKNOWN | only at ~2.5 bpw | new |
| Block-sparse attention on all layers (MiniMax-M3.1) | full KV kept (123 KB/token) — sparsity saves compute, not memory | sparse | UNKNOWN | no (KV too large) | new |

Key point: **sparse attention (QSA, DSA, MiniMax block-sparse) saves compute, not memory** — the full KV is still stored so any block can be selected. Linear/recurrent layers are what save memory.

## HGA / HyGA investigation (required by brief)

Brief item → finding:

1. What it does: "Hybrid Gated Attention" (arXiv 2608.11805, Aug 2026) adds two gates to gated attention — one driven by the attention output (H-gate) and a cross-head gate (C-gate) — plus low-rank gate factorization and a learnable attention sink. (VERIFIED)
2. Memory: no reduction in KV cache; the low-rank gates cut *gate* parameters by ~74%. (VERIFIED)
3. Compute: negligible change. (VERIFIED)
4–5. Long-range retrieval / reasoning: **not tested** — only short benchmarks (+1.5 avg on a 5B MoE, +1.1 on Qwen3-0.6B). (VERIFIED)
6. Real weights: **none released**. (VERIFIED)
7–10. Implementation / Blackwell / 256K / quantization: no inference implementation exists. (VERIFIED)

Name collisions to avoid: **HGCA** (arXiv 2507.03153) is a hybrid GPU–CPU *attention offloading* method for inference, unrelated to model architecture. If "HGA" in the brief meant "hybrid gated (delta-net) attention" generally, that family is exactly what Qwen3.8 uses and is covered above.

**Conclusion:** HyGA is a training-time quality tweak at small scale. It is not a deployment path and does not help fit 256K on this hardware. (Decision: REJECT for deployment; revisit if a large model adopts it.)

## What to test because of architecture

- QSA's block indexer is the riskiest component: retrieval of a single needle depends on the indexer selecting its block. Needle and multi-needle tests at varied depths are mandatory for Flash-Next.
- Recurrent-state models can "smear" exact strings over long distances. Use exact-string retrieval (IDs, hashes), not only semantic recall.
- Quantization interaction: recurrent state and the indexer are sensitive; keep SSM/GDN state and indexer weights at higher precision where the quant allows (the Unsloth UD and ISTA allocations do this — verify in tensor maps).
