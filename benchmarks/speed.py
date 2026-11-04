#!/usr/bin/env python3
"""Short speed probe: fixed ~4K-token code prompt, fixed 1024-token generation, 3 repeats.
Reports prefill tok/s, decode tok/s, and speculative-draft acceptance when present.
  speed.py --label X --out results/raw/speed/X.json
"""
import argparse, json, os, statistics, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.expanduser("~/llama.cpp-lrr/src/llama-model.cpp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=1024)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    code = open(SRC, errors="replace").read()[:14000]
    msgs = [{"role": "user", "content": "Explain, step by step, what this C++ code does and list any bugs you see.\n\n" + code}]
    prompt = requests.post(f"{a.url}/apply-template", json={"messages": msgs}).json()["prompt"]
    runs = []
    for i in range(a.reps):
        r = requests.post(f"{a.url}/completion", json={"prompt": prompt, "n_predict": a.n, "temperature": 0.6, "top_p": 0.95,
                                                       "top_k": 20, "seed": 7 + i, "cache_prompt": False, "ignore_eos": True}, timeout=3600).json()
        t = r.get("timings", {})
        runs.append(dict(prompt_n=t.get("prompt_n"), pp_tps=t.get("prompt_per_second"), tg_n=t.get("predicted_n"),
                         tg_tps=t.get("predicted_per_second"), draft_n=t.get("draft_n"), draft_accepted=t.get("draft_n_accepted")))
        print(json.dumps(runs[-1]), flush=True)
    s = dict(label=a.label, runs=runs, pp_tps_median=statistics.median(x["pp_tps"] for x in runs),
             tg_tps_median=statistics.median(x["tg_tps"] for x in runs))
    if runs[0].get("draft_n"):
        s["draft_accept_rate"] = sum(x["draft_accepted"] or 0 for x in runs) / max(1, sum(x["draft_n"] or 0 for x in runs))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(s, open(a.out, "w"), indent=1)
    print(f"SPEED {a.label}: prefill {s['pp_tps_median']:.0f} tok/s, decode {s['tg_tps_median']:.1f} tok/s"
          + (f", draft accept {s['draft_accept_rate']:.2f}" if "draft_accept_rate" in s else ""), flush=True)


if __name__ == "__main__":
    main()
