# Resource Budget Tracker

| Resource | Budget | Used | Notes |
|---|---:|---:|---|
| Active engineering hours | 45 h | ~1.6 h (wall clock 16:45–18:21, 2026-11-02) | Phases 1–6 in progress |
| Unattended compute (model testing) | 72 h | ~0.9 h | 14 long-context runs so far |
| Max single long-context experiment | 24 h | — | |
| Fine-tuning PoC | 24 h | 0 h | |
| Model weights (new) | 400 GB | ~216 GB | Qwen3.8-Flash-Next Q4 111 GB, Super NVFP4 77 GB, Bolt 22 GB, Qwen MTP 4 GB |
| Quantization/conversion | 150 GB | 0 GB | |
| Datasets/repos | 50 GB | 0.6 GB | ~/llama.cpp-lrr checkout + build |
| Logs/temp | 50 GB | <0.01 GB | |
| External API | $50 | $0 | Opus comparison uses the Claude subscription (claude -p), not the API |
| Peak VRAM (PRO 4000) | 24,467 MiB | 23,150 MiB | Bolt at 272K window |
| Peak RAM | ~112 GB usable | server RSS 91.6 GB (Qwen, mostly mmapped weights) | swap traffic small; see monitor CSVs |

## Phase log

| Phase | Budget | Actual | Status |
|---|---:|---:|---|
| 1 Environment discovery | 2 h | 0.5 h | done |
| 2 Literature & model research | 7 h | 0.5 h | initial pass done; deeper reading only where needed |
| 3 Candidate triage | 4 h | 0.2 h | done |
| 4 Hardware feasibility | 4 h | 0.2 h | estimates done; measurements in Phase 6 |
| 5 Benchmark infrastructure | 6 h | 0.5 h | long-context harness (easy+hard), monitor; +0.3 h fixing CUDA 12/13 build mix |
| 6 Candidate benchmarking | 10 h | | |
| 7 Quant & inference optimization | 5 h | | |
| 8 Fine-tuning feasibility | 2 h | | |
| 9–11 Final analysis & deployment | 5 h | | |

## Deviations / approvals

- 2026-11-02: Ollama moved to the 5050 for the project duration (approved).
- 2026-11-02: Building fresh llama.cpp in ~/llama.cpp-lrr (approved).
- 2026-11-02: Adam: Opus comparison runs on his Claude subscription via `claude -p` (claude.ai auth), NOT the API. API spend stays $0.
- 2026-11-02: MiniMax-M3 (Adam's subscription, api.minimax.io/anthropic, no weekly cap) available as LLM judge for open-ended tasks and as a cloud reference model. $0 API spend.
- 2026-11-02 ~19:50: Opus AIME batch hit Adam's 5-hour Claude limit after 7/15 problems. Opus work paused pending his go-ahead.
- Interpretation: "≥262,144 input tokens" needs a window > 262,144. Native-262K models (Qwen3.8, Bolt) need an extension for the strict test: Qwen via official YaRN (class 2); Bolt via GGUF metadata override (EXPERIMENTAL). Super is native 1M.

## Final accounting (2026-11-03 19:17)

See `final-report.md` §11. Active engineering ~9 h of 45; unattended GPU ~23 h of 72; weights 279 GB of 400; API $0 of $50. No ceiling exceeded.
