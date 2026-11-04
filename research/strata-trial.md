# Strata NVFP4 trial (2026-11-04)

Engine: sergqwer/strata-nvfp4 @ 586dc5e (fork of Niko1221/Strata), source-built on Linux in `~/strata-nvfp4/build-cuda13` (CUDA 13.0 + cuBLAS 13, sm_120), with its pinned llama.cpp 3cf0325. Model: `Maximilian228/Qwen3.8-Flash-Next-NVFP4-GPTQ-Strata` (all files SHA-256 verified). Config: `configs/strata-gptq-288k.json` (294,912 window, int8 KV with 32K resident in VRAM, RoPE dynamic → YaRN past 262,144, MTP drafting, auto expert cache). Server on :8091 via `scripts/serve_strata.sh`.

## 256K qualification: PASS (10/10)

Same seeds (101–110) and scorer as the llama.cpp PASS series; token counts are the server's own `usage.prompt_tokens`.

| | llama.cpp Q4 (UD-Q4_K_XL) | Strata NVFP4 GPTQ |
|---|---|---|
| Score | 13/13 on 10/10 | **13/13 on 10/10** |
| Input tokens | 262,169–262,376 | 262,321–262,490 |
| Prompt reading at 262K | 343 s (~765 tok/s) | **92 s (~2,857 tok/s)**, 3.7× |
| Generation at 262K | 29.7 tok/s | **102.6 tok/s**, 3.5× |
| Longest run, wall clock | 13.0 min | **3.3 min** |
| Peak VRAM | 19.4 GB | 23.4 GB |
| Peak engine RSS | 91 GB (mmapped) | 75.7 GB |
| Swap-in per run | ≤ 71 MB | ≤ 172 MB |
| Peak GPU temp | 89 °C | 90 °C |

Short prompt (3.8K tokens, thinking off): generation 110.7 tok/s vs 33.7; cold prompt reading 2,131 vs 866 tok/s. 64K run: 13/13, 3,047 tok/s prompt reading.

Quality reference (vendor's table, not re-measured here): same-top-token agreement with Q8_0 93.6% (NVFP4 GPTQ) vs 94.1% (UD-Q4_K_XL).

## Caveats

- Young third-party project (one maintainer; Linux build not run by its author). Known open issue upstream: a long conversation can occasionally turn a reply into "!".
- Uses ~4 GB more VRAM (expert cache fills the card), so nothing else can share the PRO 4000 while it runs.
- Its Anthropic `count_tokens` differs from the real prompt when thinking is off (harmless for normal use).
- AIME / coding / agentic suites not yet re-run on Strata.
