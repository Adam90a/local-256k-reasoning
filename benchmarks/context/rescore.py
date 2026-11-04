#!/usr/bin/env python3
"""Re-score saved longctx results with the current scorer. NOTE: answer_tail holds the last 4000 chars, enough for the final JSON."""
import glob, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from longctx import score
for f in sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "results/raw/*/*_s*_*[0-9].json")):
    d = json.load(open(f)); d["scores"] = score(d["answer_tail"], d["expected"]); json.dump(d, open(f, "w"), indent=1, default=str)
    s = d["scores"]; bad = [k for k, v in s.items() if not k.startswith("_") and not v["ok"]]
    print(f"{f}: score={s['_score']:.2f} json={s['_json_ok']} bad={bad}")
