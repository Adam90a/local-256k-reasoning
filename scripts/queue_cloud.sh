#!/usr/bin/env bash
# Cloud reference runs (subscriptions only). Usage: queue_cloud.sh <opus|minimax>.
# Resumable. Usage limits: cloud_run.py waits for the reset and retries (Adam's instruction).
# Other failures: wait 10 min and retry the step, up to 6 times.
set -uo pipefail
cd ~/local-reasoning-research
B=$1; D=$([ $B = opus ] && echo opus-5-5 || echo minimax-m3)
PY=~/venv/bin/python
step() { for i in 1 2 3 4 5 6; do "$@" && return 0; echo "RETRY $i in 10 min: $*"; sleep 600; done; echo "STOPPED: $*"; return 1; }
for T in aime lcb; do
  step $PY benchmarks/cloud/cloud_run.py --backend $B --task $T --out results/raw/quality/$D/$T.jsonl || exit 1
done
for s in 21 22 23; do
  O=results/raw/cloud/$D/v2_262144_s$s.json
  [ -f $O ] || step $PY benchmarks/cloud/cloud_run.py --backend $B --task longctx --prompt-file results/prompts/v2/262144_s$s.json --out $O || exit 1
done
echo "CLOUD_DONE $B $(date +%T)"
