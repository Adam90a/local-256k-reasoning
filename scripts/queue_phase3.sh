#!/usr/bin/env bash
# Phase 3 (PRO 4000 only): Qwen 256K stability x10, Qwen 512K x2, Super 512K + ~1M.
set -uo pipefail
cd ~/local-reasoning-research
start() { pkill -x llama-server; sleep 5; nohup ./scripts/serve.sh $1 > results/raw/logs/server-phase3-$2.log 2>&1 &
          for i in $(seq 1 300); do curl -sf localhost:8090/health >/dev/null && { echo "SERVER UP $2 $(date +%T)"; return 0; }; sleep 3; done; echo "SERVER FAILED $2"; return 1; }
run() { ./scripts/run_ctx.sh "$@" 2>&1 | grep -E '^\[done\]|BAD|peaks|Error|Traceback'; }

start configs/qwen38fn-q4-yarn2-288k.env qwen-stability && {
  echo "== qwen stability $(date +%T)"
  for s in $(seq 101 110); do run STABILITY-v2-qwen38fn-q4-yarn2-288k 262144 $s 32768; done
  echo "STABILITY_DONE $(date +%T)"; }

start configs/qwen38fn-q4-yarn4-544k.env qwen-512k && {
  echo "== qwen 512k $(date +%T)"
  for s in 201 202; do run qwen38fn-q4-yarn4-544k-q8kv 524288 $s 32768; done; }

start configs/super-nvfp4-1m.env super-1m && {
  echo "== super 512k/1m $(date +%T)"
  run super-nvfp4-1m-q8kv 524288 301 32768
  run super-nvfp4-1m-q8kv 1000000 302 32768; }

pkill -x llama-server
echo "PHASE3_DONE $(date +%T)"
