#!/usr/bin/env bash
set -uo pipefail
cd ~/local-reasoning-research
while pgrep -f 'queue_agentic[.]sh' >/dev/null; do sleep 15; done
curl -sf localhost:8090/health >/dev/null || { nohup ./scripts/serve.sh configs/qwen38fn-q4-288k-agentic.env > results/raw/logs/server-agentic2.log 2>&1 &
  for i in $(seq 1 300); do curl -sf localhost:8090/health >/dev/null && break; sleep 3; done; }
echo "SERVER READY agentic2 $(date +%T)"
for n in 1 2 3; do ./benchmarks/agentic/run_agentic.sh qwen38fn-q4-task2-run$n task2 2>&1 | grep AGENTIC; done
pkill -x llama-server; echo "AGENTIC2_DONE $(date +%T)"
