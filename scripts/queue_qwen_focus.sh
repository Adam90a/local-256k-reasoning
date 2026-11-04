#!/usr/bin/env bash
# Qwen3.8-Flash-Next focus: speed options, same-prompt comparison with cloud, 3-bit quantization study. PRO 4000 only.
set -uo pipefail
cd ~/local-reasoning-research
export LRR_SCRATCH=/tmp/claude-1000/-home-adam/aee8f88e-e0a7-4d76-9aed-0c7c432b0b53/scratchpad/lcb-runs
while pgrep -f 'queue_super1m[.]sh' >/dev/null; do sleep 30; done
start() { pkill -x llama-server; sleep 5; nohup ./scripts/serve.sh $1 > results/raw/logs/server-focus-$2.log 2>&1 &
          for i in $(seq 1 300); do curl -sf localhost:8090/health >/dev/null && { echo "SERVER UP $2 $(date +%T) vram=$(nvidia-smi -i 0 --query-gpu=memory.used --format=csv,noheader)"; return 0; }
          pgrep -x llama-server >/dev/null || break; sleep 3; done; echo "SERVER FAILED $2"; tail -n 5 results/raw/logs/server-focus-$2.log; return 1; }
speed() { ~/venv/bin/python benchmarks/speed.py --label $1 --out results/raw/speed/$1.json 2>&1 | grep SPEED; }
canon() { for s in 21 22 23; do ~/venv/bin/python benchmarks/context/longctx.py --prompt-file results/prompts/v2/262144_s$s.json --tokens 262144 \
            --max-new 32768 --label $1 --out results/raw/$1/v2_262144_s$s.json 2>&1 | grep -E '^\[done\]|BAD'; done; }

start configs/qwen38fn-q4-yarn2-288k.env q4-base && { speed q4-base; echo "== q4 canonical $(date +%T)"; canon CANON-qwen38fn-q4-288k; }
start configs/qwen38fn-q4-288k-mtp.env q4-mtp && { speed q4-mtp; ./scripts/run_ctx.sh SPEED-qwen38fn-q4-288k-mtp 262144 120 32768 2>&1 | grep -E '^\[done\]|BAD'; }
start configs/qwen38fn-q4-288k-gpu3.env q4-gpu3 && { speed q4-gpu3; ./scripts/run_ctx.sh SPEED-qwen38fn-q4-288k-gpu3 262144 120 32768 2>&1 | grep -E '^\[done\]|BAD'; }

while ! grep -q 'exit=0' /tmp/claude-1000/-home-adam/aee8f88e-e0a7-4d76-9aed-0c7c432b0b53/tasks/bhs8p70vy.output 2>/dev/null; do sleep 30; done
start configs/qwen38fn-iq3s-yarn2-288k.env iq3s && {
  speed iq3s; echo "== iq3s canonical $(date +%T)"; canon CANON-qwen38fn-iq3s-288k
  echo "== iq3s aime $(date +%T)"
  ~/vllm-env/bin/python benchmarks/reasoning/quality.py --task aime --out results/raw/quality/qwen38fn-iq3s/aime.jsonl \
      --temperature 0.6 --top-p 0.95 --top-k 20 2>&1 | tee -a results/raw/quality/qwen38fn-iq3s/aime.log | grep -E 'SUMMARY'; }
pkill -x llama-server
echo "FOCUS_DONE $(date +%T)"
