#!/usr/bin/env bash
# Finalist weights -> shared HF cache (~/.cache/huggingface/hub). Resumable.
set -euo pipefail
HF=~/venv_huggingface-cli/bin/hf
$HF download nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB-GGUF NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB.gguf
echo BOLT_DONE
$HF download unsloth/Qwen3.8-Flash-Next-GGUF --include "UD-Q4_K_XL/*"
echo QWEN_FN_Q4_DONE
$HF download ggml-org/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-GGUF NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4.gguf
echo SUPER_NVFP4_DONE
echo DOWNLOADS_DONE
