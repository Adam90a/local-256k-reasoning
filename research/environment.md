# Phase 1 — Environment Discovery

Collected 2026-11-02. All values MEASURED on this workstation unless labeled.

## Hardware

| Item | Value |
|---|---|
| CPU | AMD Ryzen Threadripper 7970X, 32C/64T, 1 socket, 1 NUMA node, 128 MiB L3 (4 CCD) |
| RAM | 4 × 32 GB DDR5 @ 4800 MT/s (4 channels populated) — 125 GiB visible |
| RAM bandwidth (theoretical) | 4 ch × 4800 MT/s × 8 B ≈ 153.6 GB/s (ESTIMATED; measure in Phase 4) |
| Swap | 64 GB file (/swap.img, unused) + 16 GB zram (12.6 GB in use) |
| THP | madvise |
| Project GPU | GPU 0, RTX PRO 4000 Blackwell, bus 01:00.0, 24,467 MiB, 145 W limit, SM 12.0, PCIe Gen5 x16 max, SM 3090 MHz max, mem 14001 MHz |
| Excluded GPU | GPU 1, RTX 5050 8 GB, bus 81:00.0 — NOT USED by this project |
| Storage | Corsair MP600 PRO 7.3 TB (root, 4.7 TB free); Samsung 970 EVO Plus 2 TB |

## Software

| Item | Value |
|---|---|
| OS | Ubuntu 24.04.4 LTS, kernel 7.0.0-38-generic |
| NVIDIA driver | 595.91.07 (brief said 595.71.05 — has been updated) |
| CUDA toolkits | 12.0 (system nvcc), 12.8, 13.0 in /usr/local |
| vLLM | 0.29.0, torch 2.13.0+cu130 (~/vllm-env and ~/.venv-vllm) |
| llama.cpp | ~/llama.cpp @ 581e8ec (2026-06-15), CUDA arch 120, FA on — ~4.5 months old |
| SGLang / TensorRT-LLM / ik_llama.cpp / KTransformers | not installed |

## GPU occupancy at discovery

- GPU 0 (PRO 4000): 111 MiB used, no compute processes.
- GPU 1 (5050): Anastasio bridge (2.0 GB), SwarmUI ComfyUI backend (84 MiB).

## Services that can claim the PRO 4000

| Service | State | Notes |
|---|---|---|
| ollama.service (:11434) | running, idle (no model loaded) | `CUDA_VISIBLE_DEVICES=0`, keep_alive 30m, max 3 loaded. Used by Open WebUI, ollama-gate (Rabbit R1), bridge chat. **Will collide with 256K runs.** |
| vllm-sleep-proxy (:8006 → :8005) | running, upstream down | inert while nothing listens on :8005 |
| vllm-gemma3-27b-nvfp4 (:8003) | disabled, stopped | brief's "existing deployment" is not running |
| vllm-qwen3.8-27b-nvfp4 (:8004) | disabled, stopped | |
| vllm-qwen36 (:8000) | disabled, stopped | Qwen3.6-35B-A3B NVFP4 already configured at 262,144 ctx |
| anastasio-qwen-879x | disabled | on-demand TTS renders |

## Existing local weights relevant to the project

- `~/.cache/huggingface/hub` (101 GB): nvidia/Qwen3.6-35B-A3B-NVFP4, nvidia/Qwen3.8-27B-NVFP4, RedHatAI/Qwen3.8-27B-INT4, nvidia/Gemma-4-26B-A4B-NVFP4, MiniMaxAI/MiniMax-M3, Qwen3-Coder-30B-A3B (HF + unsloth GGUF).
- `~/models` (27 GB): Gemma-3-27B-it-nvfp4, Qwen3.6-35B-A3B-NVFP4, Qwen3.8-27B-NVFP4.
- `~/.ollama/models` 23 GB.

## Storage headroom

4.7 TB free on root. Project allowance 650 GB is well within free space.

## Other PRO 4000 claimants (not running at discovery)

- Unmute voice stack (~/unmute docker compose): STT/TTS containers are configured for the PRO 4000 but were not running (only traefik/frontend/backend up). Must stay down during GPU runs.

## Change made in Phase 1 (approved by Adam: "Move Ollama to the 5050")

- Added `~/.config/systemd/user/ollama.service.d/zz-lrr-project-gpu1.conf`: `CUDA_VISIBLE_DEVICES=1`, `OLLAMA_VULKAN=0`, `GGML_VK_VISIBLE_DEVICES=-1`.
- Finding: Ollama had `OLLAMA_VULKAN=true`; its Vulkan backend ignores `CUDA_VISIBLE_DEVICES`, so CUDA-index pinning alone did not move it. Verified after the change: Ollama runner on bus 81:00.0 (5050).
- Revert: delete the file, `systemctl --user daemon-reload && systemctl --user restart ollama`.

## Build gotcha (2026-11-02)

First llama.cpp build compiled with nvcc 13.0 but CMake's FindCUDAToolkit picked the system CUDA 12 runtime (`/usr/lib/x86_64-linux-gnu/libcudart.so`, `/usr/bin` toolkit). CUDA 13 changed `cudaDeviceProp`, so `sharedMemPerBlockOptin` read as 4294967297 → kernels launched with any dynamic shared memory failed with "invalid argument" (seen first on Nemotron Bolt's MoE path). Fix: configure with `-DCUDAToolkit_ROOT=/usr/local/cuda-13.0` and `PATH=/usr/local/cuda-13.0/bin:$PATH`; CUDA 13.0 has no cuBLAS installed, so cuBLAS 13 headers/libs come from `~/vllm-env/.../nvidia/cu13` (`-isystem` + explicit `CUDA_cublas*_LIBRARY` + build RPATH). Verified with `ldd`: cudart.so.13, cublas.so.13, cublasLt.so.13.
