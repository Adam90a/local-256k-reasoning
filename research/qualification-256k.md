# 256K Operational Qualification — Qwen3.8-Flash-Next (brief §4.4)

**Label: PASS** (class 2: officially extended configuration — Qwen's documented YaRN method).

Date: 2026-11-03, 09:09–11:00. Config: `configs/qwen38fn-q4-yarn2-288k.env` (Unsloth UD-Q4_K_XL GGUF, llama.cpp 29c720e, window 294,912 = 262,144 input + 32,768 output, YaRN factor 2 / original 262,144, f16 KV, routed experts + n-gram table in system RAM, everything else on the RTX PRO 4000). Raw data: `results/raw/STABILITY-v2-qwen38fn-q4-yarn2-288k/`.

## Criteria (brief §4.4) — all MEASURED

| # | Criterion | Result |
|---|---|---|
| 1 | ≥ 262,144 actual input tokens | 262,169 – 262,376 per run |
| 2 | Tokenizer-confirmed count | counted by the serving model's own `/tokenize` on the fully templated prompt; server-reported `prompt_n` matches |
| 3 | Chat-template overhead included | yes — count is of the rendered template |
| 4 | No silent truncation | `truncated=false` on all 10 |
| 5 | Generation completes | all 10 stopped on EOS with a valid JSON answer |
| 6 | No CUDA errors / OOM / crashes / corruption | none |
| 7 | Retrieval + reasoning usable | **13/13 on all 10 runs** (7 retrieval/aggregation checks, 5 cross-context reasoning tasks, 1 standing instruction). Cross-file aggregation F1: 1.0 on 9 runs, 0.857 on 1 (above the 0.8 pass bar) |
| 8 | Memory within budget | peak VRAM 19,394 MiB of 24,467; server RSS ≤ 91.2 GB (most of it memory-mapped weights) |
| 9 | No uncontrolled swapping | swap-in ≤ 71 MB per run (pre-existing zram activity from swappiness=180; no thrashing) |
| 10 | Reproducible | 10 consecutive runs, 10 different prompts (seeds 101–110: different code, needle values, depths, chains, schedules, callers) |

## Per-run figures

| seed | input tokens | prefill | output tokens | gen tok/s | wall |
|---|---:|---:|---:|---:|---:|
| 101 | 262,169 | 341 s | 8,416 | 29.6 | 10.4 min |
| 102 | 262,313 | 343 s | 6,841 | 29.7 | 9.6 min |
| 103 | 262,366 | 343 s | 9,867 | 29.7 | 11.3 min |
| 104 | 262,361 | 344 s | 7,069 | 29.7 | 9.7 min |
| 105 | 262,284 | 343 s | 8,433 | 29.6 | 10.5 min |
| 106 | 262,346 | 343 s | 10,188 | 29.6 | 11.4 min |
| 107 | 262,281 | 342 s | 12,973 | 29.7 | 13.0 min |
| 108 | 262,358 | 342 s | 8,107 | 29.6 | 10.3 min |
| 109 | 262,282 | 343 s | 11,845 | 29.7 | 12.4 min |
| 110 | 262,376 | 344 s | 10,567 | 29.7 | 11.7 min |

Prefill ≈ 765 tok/s (5.7 min) with no variance; decode 29.7 tok/s at 262K. Peak GPU temperature 88–89 °C at the 145 W limit (sustained; no throttling observed in SM clock logs).

## Debugging before the qualifying series (reported, not hidden)

- **Attempt v1 (window 278,528) — FAILED on run 2.** The window left only ~16K tokens for output after a 262K prompt. On seed 102 the model reasoned for 16,215 tokens (it was enumerating file headers for the cross-file question, not looping) and hit the window before answering → 0/13. Root cause: harness configuration, not model capacity. Fix: window 294,912 so a full 32K answer always fits. The same seed passed in v2 with 6,841 output tokens (reasoning length varies run to run). Raw data kept in `results/raw/STABILITY-v1-FAILED-window278k-qwen38fn/`.
- **Lesson for deployment:** size the window for input *plus* the longest reasoning trace, not input alone.

## Other candidates at 256K (single runs, same harness)

| Model | Strict 256K run | Label |
|---|---|---|
| Nemotron 3.5 Super (native 1M) | 11/12 (missed a rule placed at 85–95% depth) | CONDITIONAL (single run; stability suite not run) |
| Nemotron 3.5 Bolt | 10/12, needs GGUF metadata override past 262,144 | CONDITIONAL / EXPERIMENTAL |
