# Final Report — Local 256K Reasoning Model on the RTX PRO 4000

2026-11-02 16:45 → 2026-11-03 19:17. Brief: `~/Documents/LLM-slow.md`. All numbers MEASURED on this workstation unless labeled. Raw data: `results/raw/`; tables: `results/processed/`.

## 1. Executive recommendation

| Role | Pick |
|---|---|
| Best overall local model | **Qwen3.8-Flash-Next**, Unsloth UD-Q4_K_XL, llama.cpp, 288K window (YaRN ×2) |
| Best reasoning model | Qwen3.8-Flash-Next (AIME 2026: 14/15; Opus 5.5: 15/15) |
| Best 256K+ model | Qwen3.8-Flash-Next — **PASS**, 10/10 consecutive strict-256K runs, 13/13 checks each |
| Best repository / agentic coding model | Qwen3.8-Flash-Next under Claude Code — 6/6 bug-fix tasks solved, tests untouched |
| Best practical deployment | `configs/qwen38fn-q4-yarn2-288k.env` (19.4 GB VRAM, ~82 GB RAM, 5.7 min to read 262K, ~30 tok/s). Speed profile: 3-bit IQ3_S (+15–20% speed, −27 GB RAM). Agentic profile: same + patched chat template. |

One model wins every category. Nothing else that fits this machine came close at long context.

## 2. Model evaluation matrix (short form; full in `candidate-triage.csv`)

| Model | Size (total / active) | Context | Fits? | 256K | 512K | ~1M | AIME 26 | Coding (LCB hard, 32K cap) | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Qwen3.8-Flash-Next Q4** | 125B+51B n-gram / 6B | 262K native, 1M YaRN | B (GPU+RAM) | **PASS 10/10** | 13/13 ×2 | doesn't fit (KV ≈ 25 GB even q8) | 14/15 | 3/10 (7 capped) | **Winner** |
| Qwen3.8-Flash-Next IQ3_S | same, 3-bit | same | B | 3/3 shared prompts 13/13 | – | – | 13/15 | – | CONDITIONAL speed profile |
| Nemotron 3.5 Super NVFP4 | 120B / 12B | 1M native | B | 11/12 (one run) | 10/13 | executes, **no usable answer** (looped) | 13/15 | 4/10 (6 capped) | CONDITIONAL |
| Nemotron 3.5 Bolt IQ2 | 74B / 9B | 262K native | A (GPU only) | 10/12 (EXPERIMENTAL: needed metadata override) | – | – | 11/15 | 2/10 (8 capped) | fastest prefill, weakest reasoning |
| Claude Opus 5.5 (reference, subscription) | – | 1M | cloud | 13/13 ×3 shared prompts | – | – | 15/15 | 6/10 | ceiling |
| MiniMax-M3 (reference, subscription) | 427B | – | cloud | 13/13 ×3 | – | – | 13/15 | 6/10 | – |
| Rejected at triage | DeepSeek V4.x, Kimi K3, GLM-5.3, MiniMax-M3 local, Mistral Large 4… (too big); gpt-oss-120b (131K context); HyGA (paper only) | | | | | | | | |

On the three byte-identical 262K prompts, Qwen Q4, Qwen IQ3_S, Opus 5.5 and MiniMax-M3 all scored 13/13.

## 3. Hardware feasibility (measured)

| Config | VRAM | RAM (server RSS, mostly mmapped weights) | Prefill | Decode |
|---|---|---|---|---|
| Qwen Q4, 288K, f16 KV | 19.4 GB | ~91 GB | 762 tok/s @262K | 29.7 tok/s @262K, 33.7 short |
| Qwen IQ3_S, 288K | 18.2 GB | ~64 GB | 916 tok/s | 33.8 tok/s @262K, 39.0 short |
| Qwen Q4, 557K, YaRN ×4, q8 KV | 23.0 GB | ~90 GB | 707 tok/s @524K (12.4 min) | 9.6 tok/s @524K |
| Super NVFP4, 1M, q8 KV, ub 1024 | 21.4 GB | ~72 GB | 250–313 tok/s (67 min for 1M) | 8.4 tok/s @1M |
| Bolt IQ2, 272K, q8 KV, all on GPU | 23.2 GB | ~3 GB | 1,314 tok/s | 32.6 tok/s |

Longest **reliable** context (same criteria as qualification): Qwen 256K reliably demonstrated (10/10); 512K demonstrated on 2/2 runs (not a 10-run series). Super's advertised 1M executes but is not usable. GPU sits at 88–89 °C at the 145 W limit under sustained prefill, with no throttling observed.

## 4. Long-context architecture (see `architecture-research.md`)

Every strong model that fits is a **hybrid**: most layers keep a fixed-size recurrent state (Gated DeltaNet, Mamba-2, KDA) and a few keep a KV cache. Qwen3.8-Flash-Next keeps KV on 12 of 48 layers with 2 KV heads (6.4 GB at 256K). Sparse attention (Qwen's QSA, DeepSeek DSA) saves compute, not memory. **HGA / HyGA** (arXiv 2608.11805) is a small-scale training paper with no weights, no memory savings and no long-context tests, so it is not a deployment path.

## 5. Inference optimization

| Option | Result | Decision |
|---|---|---|
| llama.cpp vs vLLM | vLLM 0.29 supports the architectures, but its CPU offload re-streams weights per token; llama.cpp keeps experts in RAM and computes them on CPU | llama.cpp |
| Routed experts + n-gram table in RAM (`-ot exps=CPU`, `per_layer_token_embd=CPU`) | 19 GB VRAM, 30 tok/s | **use** |
| 3 expert layers moved to GPU | OOM: the 5.5 GB prompt-processing buffer no longer fits at 288K; 1 layer would buy ~2% | dropped |
| MTP speculative decoding (Qwen's own head) | short: decode +31% (44.2 tok/s), prefill −29%; **262K: decode −15%, prefill −15%** | off for long context; optional short-context profile |
| q8_0 KV | needed only beyond ~300K window | 557K profile only |
| Prompt batch (ub) | 4,096 fastest; must drop to 1,024 at 1M (buffer scales with window × batch), costing ~60% of prefill speed | per profile |
| Window sizing | window must cover input + longest reasoning (one stability run failed at 278K window) | rule in deployment doc |

## 6. Benchmark suite

`benchmarks/context/longctx.py` (planted facts in real source code; 7 retrieval/aggregation + 5 cross-context reasoning checks + standing instruction; exact token counts via the serving model's tokenizer with the chat template; automatic scoring; saved-prompt replay for cross-model comparison), `benchmarks/reasoning/quality.py` (AIME 2026 odd 15; LiveCodeBench v6 newest 10 AtCoder-hard, sandboxed execution, restricted unpickler), `benchmarks/cloud/cloud_run.py` (Opus via `claude -p` on the subscription; MiniMax via subscription key; auto-wait on usage limits), `benchmarks/speed.py`, `benchmarks/agentic/` (Claude Code bug-fix tasks), `scripts/monitor.py` (1 Hz VRAM/power/temp/RAM/swap). 32 git commits.

## 7. Quantization (see `quantization-study.md`)

Q4 is the highest precision that fits (Q5 needs ~129 GB resident). IQ3_S matches Q4 on every long-context check, is 15–20% faster and uses 27 GB less RAM, but missed one AIME problem Q4 solved. **Default Q4; IQ3_S as speed profile.**

## 8. Fine-tuning (see `fine-tuning-assessment.md`)

Not recommended. Not feasible on 24 GB for a 125B MoE at useful sequence lengths, and the measured gaps (frontier contest coding) are not ones a LoRA would close.

## 9. Deployment blueprint (see `deployment/README.md`)

Draft systemd user unit `deployment/qwen38fn.service` (not installed). Claude Code integration verified: `ANTHROPIC_BASE_URL=http://127.0.0.1:8090` against llama-server's `/v1/messages`, using `configs/qwen38fn-chat-template.agentic.jinja` (Qwen's template rejects the mid-conversation system messages Claude Code sends; the patch renders them inline and changes nothing else).

Agentic results (Claude Code + local Qwen, Q4, 288K):

| Task | Attempts | Pass | Tests untouched | Turns | Time |
|---|---|---|---|---|---|
| 2 cross-file bugs, one hidden behind the other (hint comments present: easy) | 3 | 3 | 3 | 11–15 | 76–134 s |
| 3 subtle bugs (float money parsing, banker's vs half-up rounding per README, 1-indexed paging), no hints | 3 | 3 | 3 | 15 | 143–206 s |

Fixes were idiomatic (Decimal with `ROUND_HALF_UP`, `Decimal(str(rate))`), not test-gaming.

## 10. Decision and 30-day roadmap

Deploy now: Qwen3.8-Flash-Next Q4, 288K profile, on demand (start the service when needed, so it does not hold 19 GB VRAM and ~82 GB RAM idle).

Next 30 days:
1. Run the 10-run stability series on the 557K profile and on IQ3_S if either becomes a daily driver.
2. Larger agentic evaluation (real repos, multi-hour sessions; compare to Opus on the same tasks).
3. Re-check llama.cpp monthly: QSA decode at 512K and MTP at long context should improve as the qwen4exp code matures.
4. Watch for Qwen4 (this architecture's successor) and any dense ≤30B long-context model that could run fully on GPU.

Remaining bottlenecks: decode speed at ≥512K (~10 tok/s), RAM bandwidth for CPU-resident experts (103 GB/s measured), single 24 GB card.

## 11. Resource accounting

| Resource | Budget | Used |
|---|---|---|
| Wall-clock | — | 26.5 h (2026-11-02 16:45 → 11-03 19:17) |
| Active engineering (excluding waits) | 45 h | ~9 h ESTIMATED (harness, debugging, analysis, writing) |
| Unattended GPU compute | 72 h | ~23 h (GPU busy nearly continuously from 17:00 day 1) |
| Longest single experiment | 24 h | 2.1 h (Super 1M) |
| Fine-tuning compute | 24 h | 0 h (not justified) |
| New model weights | 400 GB | 279 GB on disk (Qwen Q4 108 + IQ3_S 78 + Super 72 + Bolt 21; GiB) |
| Datasets / repos | 50 GB | 0.7 GB (llama.cpp checkout 570 MB, AIME + LCB v6 129 MB) |
| Logs / results | 50 GB | 16 MB |
| External API | $50 | **$0**: Opus via Adam's Claude subscription, MiniMax via subscription |
| Peak VRAM | 24.5 GB | 23.15 GB (Bolt), 23.0 GB (Qwen 557K) |
| Peak RAM (server RSS) | — | 91.6 GB (Qwen Q4, mostly mmapped weights); max swap-in 2.3 GB during Super 1M, otherwise <0.5 GB per run |

Incidents (all reported in the per-topic docs): CUDA 12/13 runtime mix in the first llama.cpp build; Opus batch hit Adam's 5-hour Claude limit (auto-wait added); MiniMax non-streaming requests hung (switched to streaming); stability v1 window too small; Super 1M and MTP OOM at default batch sizes; Qwen chat template rejected Claude Code's system messages.

## Decisions taken (2026-11-03)

1. `qwen38fn.service` installed as a user unit, **on demand** (not enabled at boot). Verified start (19.2 GB VRAM) and stop. Listed on the rig dashboard (:7999) under AI / GPU with start/stop/logs.
2. Ollama **permanently on the RTX 5050** (`ollama.service.d/gpu-5050.conf`; the old GPU-0 pin is commented out).
3. Nemotron Super, Nemotron Bolt and Qwen IQ3_S weights **deleted**; only Qwen Q4 (108 GiB) kept. Re-download commands are in `scripts/download_phase1.sh` and `quantization-study.md` if needed.

## Published (2026-11-04)

- GitHub (public): https://github.com/Adam90a/local-256k-reasoning
- Hugging Face dataset (public): https://huggingface.co/datasets/timmyGPT/local-256k-reasoning

Published from a clean copy (no LiveCodeBench data, fresh history). Code MIT, report/measurements CC BY 4.0, third-party excerpts noted in NOTICE.md.

## Hermes as a harness (2026-11-04)

Provider `qwen38fn-local` added to `~/.hermes/config.yaml` (custom provider → `http://127.0.0.1:8090/v1`, model `qwen38fn`, context 262,144; MiniMax-M3 stays the default). Backup: `config.yaml.bak-20261104-qwen38fn`.

| Check | Result |
|---|---|
| Sanity question | correct |
| 150K-token long-document task (same scorer) | 13/13, 4.4 min |
| 3-bug fix task (same as Claude Code test), normal approvals, no `--yolo` | all tests pass, tests untouched, 2.4 min; same fixes as Claude Code |

Caveat: Hermes sends ~78K tokens of system prompt + tool definitions per new conversation → ~100 s before the first reply (follow-ups reuse the cached prefix) and ~184K of the 262K window left for content. Good fit for long-document / research work in Hermes; not a replacement for MiniMax in everyday chat.

## Engine switch to Strata (2026-11-04)

Strata NVFP4 (sergqwer fork, source-built for Linux/CUDA 13) with `Maximilian228/Qwen3.8-Flash-Next-NVFP4-GPTQ-Strata` passed the same 10-run strict-256K qualification (13/13 every run, 262,321–262,490 input tokens) at **92 s prompt reading and 102.6 tok/s** at 262K, versus 343 s and 29.7 tok/s on llama.cpp. Casual chat replies ~1 s; Hermes cold start 28 s (was 104 s); Claude Code solved the 3-bug task in 32 s (was 143–206 s) without the template patch. Now primary; llama.cpp is the fallback. Details: `strata-trial.md`.
