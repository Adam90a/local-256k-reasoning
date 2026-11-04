#!/usr/bin/env bash
# Strata NVFP4 (sergqwer fork) server on the RTX PRO 4000 ONLY, port 8091. Usage: serve_strata.sh <config.json>
set -euo pipefail
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=GPU-4e9ed5ea-d6d0-183f-9335-fd87f65d3f16
cd ~/strata-nvfp4
exec .venv/bin/python -m serve.server --engine strata --config "$1" --port ${PORT:-8091}
