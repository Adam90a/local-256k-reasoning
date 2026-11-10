# local-256k-reasoning

Which open-weight model gives the best **reasoning with ≥256K tokens of reliable context** on one 24 GB GPU plus 128 GB of RAM, and which engine should run it? A measured answer, from November 2026.

Also on Hugging Face: [datasets/timmyGPT/local-256k-reasoning](https://huggingface.co/datasets/timmyGPT/local-256k-reasoning).

**Hardware:** RTX PRO 4000 Blackwell (24 GB, the only GPU used) · Threadripper 7970X · 128 GB DDR5-4800 · llama.cpp `29c720e`.

## Result

**Qwen3.8-Flash-Next**, run on the **[Strata NVFP4](https://github.com/sergqwer/strata-nvfp4) engine** with the [NVFP4 GPTQ](https://huggingface.co/Maximilian228/Qwen3.8-Flash-Next-NVFP4-GPTQ-Strata) weights (routed experts in system RAM, int8 KV, 294,912-token window). llama.cpp with Unsloth's `UD-Q4_K_XL` GGUF also passes, about 3.5× slower.

- **256K qualification: PASS on both engines.** 10 consecutive runs at ≥262,144 input tokens (counted with the chat template), no truncation or errors, **13/13** on every run: 7 retrieval/aggregation checks, 5 cross-context reasoning tasks, and a standing instruction.

| At ~262K input tokens | llama.cpp (UD-Q4_K_XL) | **Strata (NVFP4 GPTQ)** |
|---|---|---|
| 10-run qualification | 13/13 ×10 | **13/13 ×10** |
| Prompt reading | 5.7 min (~765 tok/s) | **1.5 min (~2,857 tok/s)** |
| Generation | 29.7 tok/s | **102.6 tok/s** |
| Short-prompt generation | 33.7 tok/s | **110.7 tok/s** |
| Peak VRAM / engine RAM | 19.4 GB / 91 GB | 23.4 GB / 76 GB |
| Claude Code, 3-bug fix task | 2.4–3.4 min | **32 s** |

- **Same prompts as Claude Opus 5.5:** on three byte-identical 262K prompts, Qwen (both 4-bit builds), Opus 5.5 and MiniMax-M3 all scored 13/13. *On this benchmark* the local model matches Opus. The benchmark doesn't separate the top models, so this is not a claim of overall parity.
- **512K:** 13/13 on 2/2 runs (llama.cpp, YaRN ×4, q8_0 KV). About 1M does not fit.
- **AIME 2026 (15 problems):** 14/15 (Opus 5.5: 15/15). Measured on llama.cpp.
- **Claude Code / Hermes driving the local model:** all bug-fix tasks solved, tests untouched.
- **Weakest area:** hard contest coding (LiveCodeBench v6 hard: 3/10 local vs 6/10 Opus).
- **64 GB of RAM works (simulated):** about 80 tok/s decode vs about 108 with 128 GB, and about 40% slower prompt reading, in Strata's low-RAM mode ([research/low-ram-64gb.md](research/low-ram-64gb.md)).
- **Caveat on Strata:** a young, single-maintainer project (Windows-first; built from source here). AIME and coding were not re-run on it.

### All candidates (llama.cpp unless noted)

| Model (all on the same machine) | 256K | 512K | ~1M | AIME 2026 | LCB hard |
|---|---|---|---|---|---|
| **Qwen3.8-Flash-Next Q4** | **PASS 10/10** | 13/13 ×2 | doesn't fit | 14/15 | 3/10 |
| Qwen3.8-Flash-Next IQ3_S (3-bit) | 13/13 ×3 | – | – | 13/15 | – |
| Nemotron 3.5 Super NVFP4 | 11/12 | 10/13 | runs, no usable answer | 13/15 | 4/10 |
| Nemotron 3.5 Bolt IQ2 | 10/12* | – | – | 11/15 | 2/10 |
| Claude Opus 5.5 (cloud reference) | 13/13 ×3 | – | – | 15/15 | 6/10 |
| MiniMax-M3 (cloud reference) | 13/13 ×3 | – | – | 13/15 | 6/10 |

\* needed a GGUF context-length override (experimental).

Full write-up: **[research/final-report.md](research/final-report.md)** and **[research/strata-trial.md](research/strata-trial.md)**. Also: [256K qualification](research/qualification-256k.md) · [quantization study](research/quantization-study.md) · [architecture notes, including HGA](research/architecture-research.md) · [fine-tuning assessment](research/fine-tuning-assessment.md) · [64 GB of RAM](research/low-ram-64gb.md) · [deployment](deployment/README.md).

## Practical findings

- **Size the window for input plus reasoning.** A 278K window with a 262K prompt left too little room, and one run ran out of space mid-reasoning.
- **Build llama.cpp against one CUDA version.** CUDA 13 headers with the CUDA 12 runtime corrupt `cudaDeviceProp`, and every kernel needing dynamic shared memory then fails with "invalid argument". See [research/environment.md](research/environment.md).
- **MTP speculative decoding** gives +31% decode on short prompts but −15% at 262K. Keep it off for long context.
- **Qwen3.8-Flash-Next's stock chat template rejects Claude Code's mid-conversation system messages.** A one-line patched template is in `configs/`.
- **Ollama's Vulkan backend ignores `CUDA_VISIBLE_DEVICES`.** Pin it by disabling Vulkan.

## Reproduce

```bash
# Strata (recommended): build sergqwer/strata-nvfp4 for your GPU, then
scripts/serve_strata.sh configs/strata-gptq-288k.json      # paths inside the JSON point at this machine; edit them
benchmarks/context/longctx_openai.py --url http://127.0.0.1:8091 --tokens 262144 --seed 101 --out strata.json
# llama.cpp
scripts/serve.sh configs/qwen38fn-q4-yarn2-288k.env        # edit the GPU UUID in serve.sh for your card
benchmarks/context/longctx.py --tokens 262144 --seed 101 --out out.json
benchmarks/context/longctx.py --prompt-file results/prompts/v2/262144_s21.json --tokens 262144 --out same_prompt.json
benchmarks/reasoning/quality.py --task aime --out aime.jsonl   # needs benchmarks/data (see its README)
```

Licensing: code MIT; report and measurements CC BY 4.0; test prompts contain third-party source excerpts, see [NOTICE.md](NOTICE.md).

---

## Repository layout (project notes)

Execution of `~/Documents/LLM-slow.md`: find, test, and deploy the strongest local reasoning/coding model with ≥256K reliable context on this workstation, using only the RTX PRO 4000 Blackwell.

## Layout

- `research/` — environment, model research, triage (CSV + MD), architecture, hardware feasibility, budget.
- `benchmarks/context/longctx.py` — long-context qualification test (planted facts in real source code, exact token count via server tokenizer + chat template, automatic scoring).
- `scripts/serve.sh <configs/x.env>` — starts llama-server pinned to the PRO 4000 by UUID.
- `scripts/run_ctx.sh <label> <tokens> <seed>` — one test run with resource monitoring.
- `scripts/monitor.py` — 1 Hz sampler: VRAM, GPU util/power/temp/clock, RAM, swap, CPU, server RSS.
- `results/raw/<label>/` — per-run JSON, logs, monitor CSV and peaks.

## Engine

llama.cpp built from upstream commit 29c720e (2026-11-02) in `~/llama.cpp-lrr` (CUDA 13.0, sm_120). The older `~/llama.cpp` (June) is untouched.
