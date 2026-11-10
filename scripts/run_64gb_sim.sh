#!/usr/bin/env bash
# Simulate a 64 GB-RAM PC for Strata (Qwen3.8-Flash-Next NVFP4) on the PRO 4000, benchmark it, then restore the
# live service. Run in your own terminal (it asks for sudo once):  bash ~/local-reasoning-research/scripts/run_64gb_sim.sh
#
# - Stops strata.service (the PRO 4000 can't hold both) and starts a capped copy, unit strata-64g, on :8092.
# - Cap: MemoryMax (default 56G = what a 64 GB box with a desktop leaves Strata), no swap. The cap counts the file
#   cache too, so SSD expert reads behave like on a real 64 GB machine.
# - Config: configs/strata-64gb-sim.json (low-RAM mode via --ram-budget 48, KV in VRAM, 128K context,
#   its own expert-profile copy so the live profile is never touched).
# - Bench: the 11-09 validation matrix (512 output tokens, thinking off), sizes 4K/32K/128K x 2 reps by default.
# - Always restores: stops strata-64g and starts strata again on exit, even on Ctrl-C or failure.
#
# Don't edit this file while it runs (bash reads it as it goes): run a copy with ROOT=<repo>.
# Env overrides: CAP=56G  SIZES=4096,32768,131072  REPS=2  KEEP=1 (leave the sim running, don't restore)
set -euo pipefail
CAP=${CAP:-56G}
SIZES=${SIZES:-4096,32768,131072}
REPS=${REPS:-2}
ROOT=${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}   # set ROOT when running a copy from elsewhere
CFG=${CFG:-$ROOT/configs/strata-64gb-sim.json}
OUT=$ROOT/results/64gb-sim/$(date +%Y%m%d-%H%M%S)-cap$CAP
PY=/home/adam/strata-nvfp4/.venv/bin/python
UNIT=strata-64g
# No passwordless sudo -> user unit (no cache drop; oomd's user@ rule could kill it under long pressure).
if sudo -n true 2>/dev/null; then MODE=system; S=sudo; SC="sudo systemctl"; JC="sudo journalctl -u $UNIT"
  CG=/sys/fs/cgroup/system.slice/$UNIT.service
else MODE=user; S=""; SC="systemctl --user"; JC="journalctl --user -u $UNIT"
  CG=/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/$UNIT.service; fi
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
echo "== 64 GB sim: cap $CAP, sizes $SIZES x $REPS -> $OUT"

restore() {
  [[ ${KEEP:-0} == 1 ]] && { echo "KEEP=1: leaving $UNIT running on :8092 (stop: $SC stop $UNIT)"; return; }
  echo "== restoring live strata"
  [[ -n ${MON:-} ]] && kill "$MON" 2>/dev/null || true
  $JC -b --no-pager -o short-iso > "$OUT/engine-journal.log" 2>/dev/null || true
  [[ -n ${ELOG:-} ]] && cp $ELOG "$OUT/engine.log" 2>/dev/null || true
  $SC stop $UNIT 2>/dev/null || true
  $SC reset-failed $UNIT 2>/dev/null || true
  for i in $(seq 30); do $SC is-active -q $UNIT || break; sleep 2; done
  for try in 1 2 3; do
    systemctl start --no-block strata; sleep 5
    systemctl is-active -q strata && { echo "strata starting again (watch: journalctl -u strata -f)"; return; }
  done
  echo "!! strata did NOT restart - run: systemctl start strata"
}
trap restore EXIT

echo "mode: $MODE"
[[ $MODE == system ]] && sudo -v
echo "== stopping live strata"
systemctl stop strata
for i in $(seq 60); do nvidia-smi --id=GPU-4e9ed5ea-d6d0-183f-9335-fd87f65d3f16 --query-gpu=memory.used --format=csv,noheader,nounits \
  | awk '{exit !($1<2000)}' && break; sleep 2; done

echo "== dropping page cache + compacting RAM (fragmented RAM made loads take ~7 min)"
if [[ $MODE == system ]]; then sudo sh -c 'sync; echo 3 >/proc/sys/vm/drop_caches; echo 1 >/proc/sys/vm/compact_memory'
else echo "   skipped (no sudo)"; fi

ELOG=$ROOT/results/64gb-sim/engine-current.log; : > $ELOG
echo "== starting $UNIT under MemoryMax=$CAP"
T0=$(date +%s)
if [[ $MODE == system ]]; then RUN=(sudo systemd-run --uid=adam --gid=adam -p ManagedOOMPreference=avoid -p LimitMEMLOCK=infinity)
else RUN=(systemd-run --user); fi
"${RUN[@]}" --unit $UNIT \
  -p MemoryMax=$CAP -p MemorySwapMax=0 -p WorkingDirectory=/home/adam \
  -E HOME=/home/adam -E PORT=8092 \
  $ROOT/scripts/serve_strata.sh "$CFG"

# cgroup monitor: memory + NVMe reads every 2 s (low-RAM mode reads cold experts from experts.bin)
( echo "t,mem_current_gib,mem_peak_gib,anon_gib,file_gib,io_read_gib"
  set +e; while sleep 2; do [[ -r $CG/memory.current ]] || continue
    awk -v t=$(($(date +%s)-T0)) -v cur=$(cat $CG/memory.current) -v pk=$(cat $CG/memory.peak 2>/dev/null || echo 0) \
        -v rb=$(P=$(pgrep -x strata | head -1); awk '/^read_bytes/{print $2}' /proc/$P/io 2>/dev/null || echo 0) \
      '/^anon /{an=$2} /^file /{fi=$2} END{g=2^30; printf "%d,%.2f,%.2f,%.2f,%.2f,%.2f\n",t,cur/g,pk/g,an/g,fi/g,rb/g}' $CG/memory.stat
  done ) > "$OUT/cgroup.csv" &
MON=$!

echo "== waiting for :8092 to answer (up to 15 min)"
for i in $(seq 450); do
  if curl -sf -m 5 http://127.0.0.1:8092/status >/dev/null; then break; fi
  $SC is-active -q $UNIT || { echo "!! $UNIT died during load:"; $JC -b --no-pager | tail -40; exit 1; }
  sleep 2
done
curl -sf -m 5 http://127.0.0.1:8092/status >/dev/null || { echo "!! not ready after 15 min"; exit 1; }
echo "ready after $(($(date +%s)-T0)) s"
{ grep -iE 'low-ram|ram budget|ram-budget|resident|tier|expert cache|slots|pinned|GiB' $ELOG | tail -25 || true; } | tee "$OUT/load-summary.txt"

echo "== bench"
$PY $ROOT/scripts/bench_64gb_sim.py "$OUT" --sizes "$SIZES" --reps "$REPS"

echo "== summary"
$PY - "$OUT" <<'EOF'
import json, sys, csv, statistics as st
out = sys.argv[1]
rows = [json.loads(l) for l in open(f"{out}/raw-results.jsonl")]
base = {"4k": "2.0 s / 109.8", "32k": "11.4 s / 107.5", "64k": "21.6 s / 101.5", "128k": "43.5 s / 100.2"}
by = {}
for r in rows: by.setdefault(r["label"].split("_")[0], []).append(r)
lines = ["| prompt | TTFT | prefill tok/s | decode tok/s | expert hit | 11-09 full-RAM TTFT / decode |", "|---|---|---|---|---|---|"]
f = lambda xs: round(st.mean([x for x in xs if x is not None]), 1) if any(x is not None for x in xs) else "-"
for k, rs in by.items():
    lines.append(f"| {k} | {f([r['ttft_s'] for r in rs])} s | {f([r['prefill_tok_s_server'] for r in rs])} | "
                 f"{f([r['decode_tok_s_server'] for r in rs])} | {f([r['expert_hit_rate'] for r in rs])} | {base.get(k, '-')} |")
cg = list(csv.DictReader(open(f"{out}/cgroup.csv")))
if cg:
    lines.append(f"\nRAM peak {max(float(c['mem_peak_gib']) for c in cg):.1f} GiB, "
                 f"NVMe read total {float(cg[-1]['io_read_gib']):.1f} GiB")
open(f"{out}/summary.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
EOF
echo "== done: $OUT"
