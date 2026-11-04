#!/usr/bin/env bash
# MTP retry after the focus queue (draft ubatch 512).
set -uo pipefail
cd ~/local-reasoning-research
while pgrep -f 'queue_qwen_focus[.]sh' >/dev/null; do sleep 30; done
pkill -x llama-server; sleep 5
nohup ./scripts/serve.sh configs/qwen38fn-q4-288k-mtp.env > results/raw/logs/server-focus-q4-mtp2.log 2>&1 &
for i in $(seq 1 300); do curl -sf localhost:8090/health >/dev/null && break; pgrep -x llama-server >/dev/null || { echo "SERVER FAILED q4-mtp2"; tail -n 5 results/raw/logs/server-focus-q4-mtp2.log; exit 1; }; sleep 3; done
echo "SERVER UP q4-mtp2 $(date +%T) vram=$(nvidia-smi -i 0 --query-gpu=memory.used --format=csv,noheader)"
~/venv/bin/python benchmarks/speed.py --label q4-mtp --out results/raw/speed/q4-mtp.json 2>&1 | grep SPEED
./scripts/run_ctx.sh SPEED-qwen38fn-q4-288k-mtp 262144 120 32768 2>&1 | grep -E '^\[done\]|BAD'
pkill -x llama-server; echo "MTP_DONE $(date +%T)"
