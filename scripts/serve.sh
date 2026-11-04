#!/usr/bin/env bash
# Launch llama-server on the RTX PRO 4000 ONLY (pinned by UUID). Usage: serve.sh <config.env>
# The config file sets MODEL, CTX, and EXTRA (extra llama-server args).
set -euo pipefail
source "$1"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=GPU-4e9ed5ea-d6d0-183f-9335-fd87f65d3f16   # RTX PRO 4000; never the 5050
# Build links CUDA 13 cudart + cuBLAS via RPATH (see research/environment.md). Don't set LD_LIBRARY_PATH.
set -f   # EXTRA is word-split unquoted; never glob-expand override patterns like [5-7]
PORT=${PORT:-8090}
exec ~/llama.cpp-lrr/build/bin/llama-server -m "$MODEL" -c "$CTX" --port "$PORT" --host 127.0.0.1 \
  --parallel 1 --flash-attn on --jinja --no-webui --metrics -t ${THREADS:-24} $EXTRA
