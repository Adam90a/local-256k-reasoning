# Deployment Blueprint

Status: **installed 2026-11-03** as an on-demand user service (`systemctl --user start qwen38fn`), not enabled at boot. Also on the rig dashboard (:7999).

## What to deploy

| Item | Value |
|---|---|
| Model | `Qwen/Qwen3.8-Flash-Next` (post-trained, 2026-08-27) |
| Weights | Unsloth `UD-Q4_K_XL` GGUF, 4 shards, 111.3 GB, snapshot `766911a6…` in `~/.cache/huggingface/hub/models--unsloth--Qwen3.8-Flash-Next-GGUF` |
| Engine | llama.cpp `29c720e` (2026-11-02) at `~/llama.cpp-lrr/build/bin/llama-server`, CUDA 13.0 runtime + cuBLAS 13 (see `research/environment.md` for the build recipe) |
| GPU | RTX PRO 4000 Blackwell only, pinned by UUID `GPU-4e9ed5ea-d6d0-183f-9335-fd87f65d3f16` |
| Placement | attention, Gated DeltaNet, shared experts, router, MTP, KV cache → GPU; routed experts (`exps`) and the n-gram table (`per_layer_token_embd`) → system RAM (memory-mapped) |
| CPU | `-t 24` (of 64 threads) |

## Profiles

| Profile | Window | Rope | KV | VRAM | Validated |
|---|---|---|---|---|---|
| **default-288k** (recommended) | 294,912 | YaRN ×2 (orig 262,144) | f16 | 19.4 GB | **PASS**: 10/10 consecutive strict-256K runs (`research/qualification-256k.md`) |
| native-256k | 262,144 | none | f16 | 18.0 GB | 64K/128K/246K runs 8/8 (no stability suite; use when prompts + answers stay < 256K) |
| long-544k | 557,056 | YaRN ×4 (official 1M recipe) | q8_0 | 23.0 GB | 2/2 runs at 524K input, 13/13 each; decode drops to ~9.6 tok/s |

Window sizing rule (learned in qualification): window ≥ largest input + 32,768 tokens of reasoning/answer.

## Measured performance (default-288k, 262K input)

- Prefill ≈ 765 tok/s → 5.7 min for 262K tokens.
- Decode ≈ 29.7 tok/s at 262K context; ~34 tok/s at short context.
- Load time ≈ 70 s (weights mmapped; first run after boot reads ~82 GB from NVMe).

## Service (user unit, not installed)

`deployment/qwen38fn.service` → copy to `~/.config/systemd/user/`, `systemctl --user daemon-reload`, then `systemctl --user start qwen38fn` (only after approval). Port 8090, localhost only.

## Claude Code integration

llama-server serves Anthropic's Messages API (`POST /v1/messages`, `/v1/messages/count_tokens`), so Claude Code can use it directly:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8090 ANTHROPIC_AUTH_TOKEN=local \
ANTHROPIC_MODEL=qwen38fn ANTHROPIC_SMALL_FAST_MODEL=qwen38fn claude
```

(To be verified end to end in Phase 10: tool calls, streaming, long sessions.)

## Monitoring

- `scripts/monitor.py <csv> <pid>`: VRAM, GPU util/power/temp/clock, RAM, swap traffic.
- llama-server `--metrics` exposes Prometheus metrics on `/metrics`.
- Rig dashboard (:7999) already shows GPU state.

## Recovery

1. `systemctl --user restart qwen38fn` (weights reload from page cache in ~70 s).
2. If CUDA errors mention "invalid argument" at kernel launch → the binary picked up a CUDA 12 runtime; check `ldd ~/llama.cpp-lrr/build/bin/libggml-cuda.so | grep -E 'cudart|cublas'` shows `.so.13` from `nvidia/cu13`.
3. If the GPU is busy → Ollama must stay off the PRO 4000 (see the temporary drop-in noted in `research/environment.md`; a permanent answer is needed before revert).
4. OOM at startup with large windows → lower `-ub` (compute buffer scales with window × ubatch).

## Open decisions for Adam

- Enable the service at boot, or start on demand?
- Ollama placement after the project: revert to the PRO 4000 (conflicts with this model) or keep it on the 5050?
