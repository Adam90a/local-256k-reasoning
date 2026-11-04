#!/usr/bin/env bash
# Claude Code driven by the LOCAL llama-server (Anthropic /v1/messages). No Anthropic usage: base URL is localhost.
# Usage: run_agentic.sh <label>   (server must already be up on :8090)
set -uo pipefail
LABEL=$1; TASK=${2:-task1}
R=~/local-reasoning-research
W=/tmp/claude-1000/-home-adam/aee8f88e-e0a7-4d76-9aed-0c7c432b0b53/scratchpad/agentic-$LABEL-$(date +%H%M%S)
rm -rf $W; cp -r $R/benchmarks/agentic/$TASK-template $W; cd $W
TESTHASH=$(cat tests/*.py run_tests.py | sha256sum | cut -d" " -f1)
PROMPT='The tests in this repository fail. Run `python3 run_tests.py` to see the failures, find and fix the bugs in the package (read README.md first if present), and re-run the tests until they all pass. Do not modify anything under tests/ or run_tests.py. When done, reply with a one-paragraph summary of each bug and its fix.'
T0=$(date +%s)
env -u ANTHROPIC_API_KEY ANTHROPIC_BASE_URL=http://127.0.0.1:8090 ANTHROPIC_AUTH_TOKEN=local-llama \
    ANTHROPIC_MODEL=qwen38fn ANTHROPIC_SMALL_FAST_MODEL=qwen38fn ENABLE_CLAUDEAI_MCP_SERVERS=false \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
  timeout 3600 claude -p "$PROMPT" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --no-session-persistence \
    --permission-mode acceptEdits --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "Bash(python3 run_tests.py)" \
    --max-turns 40 --output-format json > $W/claude_out.json 2> $W/claude_err.log
RC=$?; T1=$(date +%s)
python3 run_tests.py > $W/final_tests.txt 2>&1; TESTS_RC=$?
NEWHASH=$(cat tests/*.py run_tests.py | sha256sum | cut -d" " -f1)
python3 - "$W" "$LABEL" "$RC" "$TESTS_RC" "$((T1-T0))" "$TESTHASH" "$NEWHASH" <<'PY'
import json, sys, os
w, label, rc, trc, secs, h0, h1 = sys.argv[1:]
try: d = json.load(open(os.path.join(w, "claude_out.json")))
except Exception as e: d = {"parse_error": str(e)}
res = dict(label=label, claude_exit=int(rc), tests_pass=int(trc) == 0, tests_untouched=h0 == h1, wall_s=int(secs),
           num_turns=d.get("num_turns"), is_error=d.get("is_error"), result=(d.get("result") or "")[:1500],
           final_tests=open(os.path.join(w, "final_tests.txt")).read()[-600:], workdir=w)
os.makedirs(os.path.expanduser("~/local-reasoning-research/results/raw/agentic"), exist_ok=True)
json.dump(res, open(os.path.expanduser(f"~/local-reasoning-research/results/raw/agentic/{label}.json"), "w"), indent=1)
print(f"AGENTIC {label}: tests_pass={res['tests_pass']} tests_untouched={res['tests_untouched']} turns={res['num_turns']} wall={secs}s exit={rc}")
PY
