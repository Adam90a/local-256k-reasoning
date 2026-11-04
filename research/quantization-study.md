# Quantization Study — Qwen3.8-Flash-Next (brief §13)

Date 2026-11-03. Both builds served by the same llama.cpp (29c720e), same 288K strict-256K config (YaRN ×2, f16 KV, routed experts + n-gram table in RAM), same harness and seeds. All values MEASURED.

## Builds

| | Unsloth UD-Q4_K_XL | ISTA-DASLab GSQ-RCO IQ3_S |
|---|---|---|
| Size on disk | 111.3 GB (4 shards) | 83.6 GB (2 shards) |
| Transformer weights (must be resident) | ~82 GB | 54.8 GB |
| n-gram table (memory-mapped) | 28.8 GB IQ4_NL | 28.8 GB IQ4_NL (same) |
| Method | dynamic per-tensor 4/5/8-bit (Q4_K / Q5_1 experts) | learned scalar quantization + Riemannian budget allocation, ~3.4 bpw on experts |

The ISTA unpruned GSQ-RCO release was used (all 512 experts); the expert-pruned "Coder" variant was not tested.

## Quality (no perplexity — task results only, as the brief requires)

| Test | Q4 | IQ3_S |
|---|---|---|
| Shared 262K prompts v2 (same text Opus/MiniMax got), 13 checks each | 13/13, 13/13, 13/13 | 13/13, 13/13, 13/13 |
| Cross-file aggregation F1 on those prompts | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| AIME 2026, 15 odd-numbered problems | 14/15 | 13/15 |
| AIME per-problem differences | — | #11: IQ3_S hit the 32K token cap; Q4 solved it. All other outcomes identical (both miss the same one). |

Interpretation: long-context retrieval and cross-context reasoning are unaffected at 262K. Hard math shows a possible small loss (one problem; within noise for n=15, but in the expected direction).

## Speed and memory

| | Q4 | IQ3_S | Change |
|---|---|---|---|
| Short prompt (~4K): prefill / decode | 866 / 33.7 tok/s | 1,042 / 39.0 tok/s | +20% / +16% |
| 262K prompt: prefill | ~762 tok/s (5.7–5.9 min) | ~916 tok/s (4.8 min) | +20% |
| 262K: decode | 29.7 tok/s | 33.8 tok/s | +14% |
| Peak VRAM (288K window) | 19.2–19.4 GB | 18.2 GB | −1 GB |
| Resident RAM for weights | ~82 GB | ~55 GB | −27 GB |

## Recommendation

- **Default: Q4 (UD-Q4_K_XL).** It is the build that passed the full 10-run 256K qualification and scored highest on AIME.
- **Speed profile: IQ3_S.** Use when throughput or RAM matters more than the last bit of hard-reasoning quality (agentic loops, or running other RAM-heavy services alongside). Label **CONDITIONAL**: passed 3/3 strict-256K runs but has not run the 10-run stability suite.
- The 27 GB of RAM IQ3_S frees is enough to keep Ollama models or another service resident without memory pressure.

## Not tested (and why)

- Q5/Q6/Q8 references: Q5_K_XL needs ~129 GB resident for the transformer weights; the box has 125 GB. Q4 is the highest precision that fits, so it served as the reference.
- IQ2-class builds (ISTA IQ2_XS 68 GB, Unsloth Q2_K_XL 79 GB): not tested; IQ3_S already showed a first sign of loss on hard math, so lower bits are unlikely to be worth it for a quality-first brief.
