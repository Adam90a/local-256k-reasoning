#!/usr/bin/env bash
# Unattended: AIME-2026 (15) + LCB-v6 hard (10) for each finalist, sequentially on the PRO 4000.
set -uo pipefail
cd ~/local-reasoning-research
export LRR_SCRATCH=/tmp/claude-1000/-home-adam/aee8f88e-e0a7-4d76-9aed-0c7c432b0b53/scratchpad/lcb-runs
PY=~/vllm-env/bin/python
# label | config | temperature top_p top_k (vendor-recommended sampling)
JOBS=(
  "super-nvfp4|configs/super-nvfp4-272k.env|1.0 0.95 0"
  "qwen38fn-q4|configs/qwen38fn-q4-256k.env|0.6 0.95 20"
  "bolt-iq2|configs/bolt-iq2-256k.env|1.0 0.95 0"
)
for job in "${JOBS[@]}"; do
  IFS='|' read -r LABEL CFG SAMP <<<"$job"; read -r T P K <<<"$SAMP"
  pkill -x llama-server; sleep 5
  nohup ./scripts/serve.sh $CFG > results/raw/logs/server-quality-$LABEL.log 2>&1 &
  for i in $(seq 1 200); do curl -sf localhost:8090/health >/dev/null && break; sleep 3; done
  D=results/raw/quality/$LABEL; mkdir -p $D
  ~/venv/bin/python scripts/monitor.py $D/monitor.csv $(pgrep -x llama-server) & MON=$!
  for TASK in aime lcb; do
    echo "== $LABEL $TASK $(date +%T)"
    $PY benchmarks/reasoning/quality.py --task $TASK --out $D/$TASK.jsonl --temperature $T --top-p $P --top-k $K 2>&1 | tee -a $D/$TASK.log
  done
  kill $MON; wait $MON 2>/dev/null
done
pkill -x llama-server
echo QUALITY_QUEUE_DONE $(date +%T)
