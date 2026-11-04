#!/usr/bin/env bash
set -uo pipefail
cd ~/local-reasoning-research
pkill -x llama-server; sleep 5
nohup ./scripts/serve.sh configs/super-nvfp4-1m.env > results/raw/logs/server-super-1m.log 2>&1 &
for i in $(seq 1 300); do curl -sf localhost:8090/health >/dev/null && break; pgrep -x llama-server >/dev/null || { echo "SERVER FAILED super-1m"; exit 1; }; sleep 3; done
echo "SERVER UP super-1m $(date +%T)"; nvidia-smi -i 0 --query-gpu=memory.used --format=csv,noheader
for spec in "524288 301" "1000000 302"; do set -- $spec; ./scripts/run_ctx.sh super-nvfp4-1m-q8kv $1 $2 32768 2>&1 | grep -E '^\[done\]|BAD|peaks|Error|Traceback'; done
pkill -x llama-server; echo "SUPER1M_DONE $(date +%T)"
