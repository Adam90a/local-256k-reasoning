#!/usr/bin/env bash
# Strata trial: 10 consecutive strict-256K runs (seeds 101-110, same as the llama.cpp PASS series), resource-monitored.
set -uo pipefail
cd ~/local-reasoning-research
D=results/raw/STABILITY-strata-gptq-288k; mkdir -p $D
PID=$(pgrep -f 'build-cuda13/strata' | head -1)
echo "== strata stability $(date +%T) engine pid=$PID"
for s in $(seq 101 110); do
  ~/venv/bin/python scripts/monitor.py $D/262144_s$s.monitor.csv $PID & MON=$!
  ~/venv/bin/python benchmarks/context/longctx_openai.py --url http://127.0.0.1:8091 --tokens 262144 --seed $s \
      --label STABILITY-strata-gptq-288k --out $D/262144_s$s.json 2>&1 | grep -E '^\[done\]|BAD|Traceback|Error'
  kill $MON; wait $MON 2>/dev/null
  echo "peaks s$s: $(tr -d '\n ' < $D/262144_s$s.monitor.csv.peaks.json)"
done
echo "STRATA_STABILITY_DONE $(date +%T)"
