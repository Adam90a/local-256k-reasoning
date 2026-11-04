#!/usr/bin/env bash
# Phase 2 unattended queue (PRO 4000 only):
#  1. Qwen3.8-Flash-Next: rerun 32K-capped LCB items with a 64K budget
#  2. Qwen3.8-Flash-Next: brief §4.4 stability suite — 10 consecutive strict-256K runs (>=262,144 input), varied seeds/needles
#  3. Super + Bolt: rerun capped LCB items at 64K
set -uo pipefail
cd ~/local-reasoning-research
export LRR_SCRATCH=/tmp/claude-1000/-home-adam/aee8f88e-e0a7-4d76-9aed-0c7c432b0b53/scratchpad/lcb-runs
PY=~/vllm-env/bin/python
start() { pkill -x llama-server; sleep 5; nohup ./scripts/serve.sh $1 > results/raw/logs/server-phase2-$2.log 2>&1 &
          for i in $(seq 1 200); do curl -sf localhost:8090/health >/dev/null && return 0; sleep 3; done; echo "SERVER FAILED $2"; return 1; }
lcb64() { # label cfg temp top_p top_k ids
  start $2 $1 || return 1
  echo "== $1 lcb64k $(date +%T)"
  $PY benchmarks/reasoning/quality.py --task lcb --max-tokens 65536 --only-ids $6 --out results/raw/quality/$1/lcb64k.jsonl \
      --temperature $3 --top-p $4 --top-k $5 2>&1 | tee -a results/raw/quality/$1/lcb64k.log; }

lcb64 qwen38fn-q4 configs/qwen38fn-q4-256k.env 0.6 0.95 20 arc196_d,arc196_c,arc196_b,arc196_a,abc400_g,abc399_e,arc195_d

start configs/qwen38fn-q4-yarn2-272k.env qwen-stability && {
  echo "== qwen stability $(date +%T)"
  for s in $(seq 101 110); do ./scripts/run_ctx.sh STABILITY-qwen38fn-q4-yarn2-272k 262144 $s 32768 2>&1 | grep -E '^\[done\]|BAD|peaks|Error'; done
  echo "STABILITY_DONE $(date +%T)"; }

lcb64 super-nvfp4 configs/super-nvfp4-272k.env 1.0 0.95 0 arc196_d,arc196_c,arc196_b,abc400_g,abc399_e,arc195_d
lcb64 bolt-iq2 configs/bolt-iq2-256k.env 1.0 0.95 0 arc196_d,arc196_c,arc196_b,arc196_a,abc400_g,abc399_e,arc195_e,arc195_d
pkill -x llama-server
echo "PHASE2_DONE $(date +%T)"
