# Hardware Feasibility (Track C) — estimates before measurement

All values ESTIMATED unless marked MEASURED. GPU = RTX PRO 4000 only.

## Measured inputs

| Quantity | Value |
|---|---|
| VRAM free at idle (GPU 0) | ~24.0 GB (MEASURED, 111 MiB used) |
| RAM available | ~103 GB at discovery (MEASURED `free`) |
| RAM read bandwidth, numpy, 16 threads | 103 GB/s (MEASURED; build running concurrently) |
| Theoretical RAM bandwidth | 153.6 GB/s (4 ch DDR5-4800) |
| PCIe | Gen5 x16 (~50 GB/s practical, ESTIMATED) |

## KV / state memory by context (bf16 KV; q8_0 halves it)

Formula for full-attention layers: 2 (K,V) × n_kv_layers × n_kv_heads × head_dim × bytes × tokens. Recurrent layers add a fixed state independent of context (tens to a few hundred MB).

| Model | KV layers × heads × dim | per token | 64K | 128K | 256K | 512K | 1M |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3.8-Flash-Next | 12 × 2 × 256 | 24.6 KB | 1.6 GB | 3.2 GB | 6.4 GB | 12.9 GB | 25.8 GB |
| Nemotron 3.5 Super | 9 × 2 × 128 | 9.2 KB | 0.6 GB | 1.2 GB | 2.4 GB | 4.8 GB | 9.7 GB |
| Nemotron 3.5 Bolt | ≤9 × 2 × 128 | ≤9.2 KB | 0.6 GB | 1.2 GB | 2.4 GB | — | — |
| Qwen3.8-27B | 16 × 4 × 256 | 65.5 KB | 4.3 GB | 8.6 GB | 17.2 GB | — | — |

Plus QSA indexer keys for Flash-Next (12 layers × 1 head × 128, compressed ×4): ~0.8 KB/token → ~0.2 GB at 256K.

## Runtime memory plan per finalist (256K)

| Model / quant | Weights total | Resident weights | GPU plan (24 GB) | RAM plan | Verdict |
|---|---:|---:|---|---|---|
| Qwen3.8-Flash-Next UD-Q4_K_XL | ~111 GB | ~82 GB (n-gram 29 GB mmapped from NVMe) | attention/GDN/shared experts/router + KV 6.4 GB + compute buffers; routed experts on CPU (`-ot exps=CPU`, then move some layers back to GPU) | ~65–70 GB experts | **B — feasible** |
| Nemotron 3.5 Super NVFP4 | 77 GB | 77 GB | mamba/attn/shared + KV 2.4 GB; experts CPU | ~60–65 GB | **B — feasible**; 1M fits too |
| Nemotron 3.5 Bolt IQ2 QAT | 22 GB | 22 GB | everything + KV at q8 (1.2 GB) | ~0 | **A — fits GPU** (tight; may spill a few layers) |
| Qwen3.8-27B NVFP4 (vLLM) / Q4 GGUF | ~17–19 GB | same | weights + q8 KV 8.6 GB ≈ 27 GB → spill | small | **A/B** — needs a few layers on CPU or q4 KV |

## Throughput estimates (to be replaced with measurements)

- Decode, Flash-Next: ~6B active ≈ 3.4 GB/token at Q4; ~70% CPU-resident → ~2.4 GB/token at ~100 GB/s → upper bound ~40 tok/s; expect 10–20.
- Decode, Super: ~12B active ≈ 6.5 GB/token → expect 6–10 tok/s.
- Prefill 256K, Flash-Next: llama.cpp streams CPU-resident expert weights to GPU per micro-batch (~65 GB / 50 GB/s ≈ 1.3 s per micro-batch; 64 micro-batches at 4,096) ≈ 1.5 min of transfer + compute ≈ 2·6e9·262144 ≈ 3.1 PFLOP → a few minutes. Expect 5–15 min total.
- Risk: sparse-attention and GDN kernels at 256K may not be as optimized as dense FA; measure.
