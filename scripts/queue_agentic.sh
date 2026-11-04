#!/usr/bin/env bash
set -uo pipefail
cd ~/local-reasoning-research
# (MTP retry already finished)
pkill -x llama-server; sleep 5
nohup ./scripts/serve.sh configs/qwen38fn-q4-288k-agentic.env > results/raw/logs/server-agentic.log 2>&1 &
for i in $(seq 1 300); do curl -sf localhost:8090/health >/dev/null && break; pgrep -x llama-server >/dev/null || { echo "SERVER FAILED agentic"; exit 1; }; sleep 3; done
echo "SERVER UP agentic $(date +%T)"
for n in 1 2 3; do ./benchmarks/agentic/run_agentic.sh qwen38fn-q4-run$n 2>&1 | grep AGENTIC; done
echo "AGENTIC_DONE $(date +%T)"
