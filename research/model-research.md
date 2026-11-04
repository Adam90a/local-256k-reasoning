# Model Research (Track A)

Survey date: 2026-11-02. Sources: Hugging Face model cards + config.json (VERIFIED), vendor benchmark tables (VERIFIED as published; NOT reproduced unless marked MEASURED), llama.cpp / vLLM source (VERIFIED). Full candidate list with decisions: `candidate-triage.csv`.

## Landscape in one paragraph

By late 2026 the strongest open-weight models (DeepSeek V4.x, Kimi K3, GLM-5.3, MiniMax-M3, Mistral Large 4, Muse Spark Open, Qwen3.8-2.4T) are 400B–2.8T parameters and cannot run on 24 GB VRAM + 125 GB RAM. The interesting tier for this workstation is **74–180B sparse hybrids with 5–12B active parameters**. These pair recurrent layers (Gated DeltaNet, Mamba-2, KDA) with a few attention layers, so 256K of context costs single-digit GB. Three of them have vendor scores at or near frontier level on coding and agent benchmarks.

## Finalists

### Qwen3.8-Flash-Next — `Qwen/Qwen3.8-Flash-Next` (2026-08-27)
| Field | Value |
|---|---|
| Parameters | 125B transformer (6B active) + 51B n-gram embedding + 4B MTP head |
| Architecture | 48 layers: 12 × (3 Gated DeltaNet + 1 Qwen Sparse Attention), MoE 512 experts / 10 routed + 1 shared, gated residual (4 branches), n-gram embedding at layer 2 |
| Context | 262,144 native; 1,000,000 with YaRN ×4 (official) |
| License | qwen-community-1.0 (custom; read before redistribution) |
| Weights | BF16 safetensors 354 GB; GGUF: Unsloth UD-Q4_K_XL 111 GB (used), ISTA-DASLab GSQ-RCO IQ3_S 83.6 GB, others |
| Engines | vLLM (Qwen4ExpForConditionalGeneration in 0.29), SGLang, TokenSpeed, llama.cpp (qwen4exp, Oct 2026) |
| Vendor scores | SWE-bench Pro 62.5, SWE-bench Multilingual 81.0, LiveCodeBench v6 91.9, GPQA-D 91.7, HLE 35.9, IFBench 81.3, NL2Repo 48.1, Toolathlon 73.5 |
| Long-context evidence | none published by vendor → measured here |
| Limitations | "experimental preview of the Qwen4 architecture"; custom license; no vendor long-context scores |

### Nemotron 3.5 Super VL 120B-A12B — `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-*` (2026-10-22)
| Field | Value |
|---|---|
| Parameters | 120B total, 12B active |
| Architecture | 88 layers: Mamba-2 + 9 attention layers (2 KV heads) + LatentMoE 512 experts / 22 active; C-RADIO vision |
| Context | 1,048,576 native |
| License | OpenMDW-1.1 (permissive) |
| Weights | BF16 241 GB; NVFP4 GGUF (ggml-org) 77 GB (used); Unsloth UD quants 46–132 GB |
| Engines | vLLM (NemotronH_Super_Omni_Reasoning_V3), llama.cpp (#30520) |
| Vendor scores | see Bolt card (parent model) — Bolt is distilled from it |
| Limitations | slower decode (12B active, 22 experts/token) |

### Nemotron 3.5 Bolt 74B-A9B 24GB — `nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB-GGUF` (2026-10-15)
| Field | Value |
|---|---|
| Parameters | 74B total, 9B active (compressed from Super via Star Elastic) |
| Architecture | Mamba-2 hybrid LatentMoE, heterogeneous expert widths per layer, top-9 |
| Context | 262,144 native |
| Weights | 22 GB native IQ2 (quantization-aware), GGUF only |
| Vendor scores | Terminal-Bench 2.1 50.98, GPQA-D 86.43, HLE 25.30, AA-LCR 64.06, BrowseComp 66.75 (beats Qwen3.6-35B on most rows) |
| Limitations | 2-bit; 256K native ceiling |

### Qwen3.8-27B — `Qwen/Qwen3.8-27B` (2026-08-14) — dense baseline, already on disk
Dense 27.8B; 48 GDN + 16 gated attention layers (4 KV heads × 256); 262K native; Apache-2.0; SWE-bench Pro 61.7, Terminal-Bench 2.1 73.0, LiveCodeBench v6 90.3. NVFP4 + INT4 copies in the local HF cache. Not yet benchmarked here (lower priority: its KV cache is ~3× Flash-Next's and vendor scores are lower).

## Cloud references (for comparison only)

- **Claude Opus 5.5** (`claude-opus-5-5`, 1M context) via Adam's Claude subscription (`claude -p`, MCP/tools disabled, `--effort high`).
- **MiniMax-M3** via Adam's MiniMax subscription (api.minimax.io/anthropic, thinking enabled).

## Notes on evidence quality

- All vendor tables are self-reported and use the vendor's own harness and reasoning effort. Qwen's table compares against "Claude-Opus-4.6 (Max)", not the current Opus.
- Independent evidence found: NVIDIA's AA-LCR / Terminal-Bench numbers for Bolt (third-party benchmarks, vendor-run). No independent long-context numbers for Flash-Next or Super were found → this project measures them.
- Several aggregator blogs found during search gave conflicting or wrong specs (e.g. active-parameter counts for Kimi K3). They were used only as leads, never as evidence.
