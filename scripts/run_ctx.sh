#!/usr/bin/env bash
# Run one long-context test against a running server, with resource monitoring.
# Usage: run_ctx.sh <label> <tokens> <seed> [max_new]
set -uo pipefail
cd ~/local-reasoning-research
LABEL=$1; TOK=$2; SEED=$3; MAXNEW=${4:-16384}; PORT=${PORT:-8090}; SUITE=${SUITE:-both}
D=results/raw/$LABEL; mkdir -p $D
STAMP=$(date +%Y%m%d-%H%M%S); BASE=$D/${TOK}_s${SEED}_$STAMP
SPID=$(pgrep -f "llama-server.*--port $PORT" | head -1)
~/venv/bin/python scripts/monitor.py $BASE.monitor.csv $SPID & MON=$!
~/venv/bin/python benchmarks/context/longctx.py --url http://127.0.0.1:$PORT --tokens $TOK --seed $SEED \
   --max-new $MAXNEW --suite $SUITE --label $LABEL --out $BASE.json 2>&1 | tee $BASE.log
RC=${PIPESTATUS[0]}
kill $MON; wait $MON 2>/dev/null
echo "peaks: $(cat $BASE.monitor.csv.peaks.json | tr -d '\n ')"
exit $RC
