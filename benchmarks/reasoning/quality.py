#!/usr/bin/env python3
"""Short-context quality suite: AIME 2026 (math reasoning) and LiveCodeBench v6 hard (coding).

Resumable: one JSONL line per item in --out; already-done items are skipped.
  quality.py --task aime --out results/raw/<label>/aime.jsonl
  quality.py --task lcb  --out results/raw/<label>/lcb.jsonl
"""
import argparse, base64, io, json, os, pickle, re, resource, subprocess, sys, tempfile, time, zlib
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SCRATCH = os.environ.get("LRR_SCRATCH", tempfile.gettempdir())


# ------------------------------------------------------------------ data

def aime_items():
    rows = json.load(open(os.path.join(DATA, "aime2026/aime2026.json")))  # converted from MathArena parquet
    rows = [r for r in rows if r["problem_idx"] % 2 == 1]          # fixed subset: 15 odd-numbered problems
    for r in rows:
        yield dict(id=f"aime26-{r['problem_idx']}", answer=int(r["answer"]),
                   prompt=r["problem"] + "\n\nPlease reason step by step, and put your final answer within \\boxed{}.")


class _NoClassUnpickler(pickle.Unpickler):
    """LCB private tests are a pickled str. Refuse any class lookup so untrusted data can't execute code."""
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"blocked class {module}.{name}")


def _private_tests(s):
    raw = zlib.decompress(base64.b64decode(s.encode()))
    obj = _NoClassUnpickler(io.BytesIO(raw)).load()
    return json.loads(obj)


def lcb_items(n=10):
    rows = [json.loads(l) for l in open(os.path.join(DATA, "lcb/test6.jsonl"))]
    rows = [r for r in rows if r["platform"] == "atcoder" and r["difficulty"] == "hard"]
    rows.sort(key=lambda r: (r["contest_date"], r["question_id"]), reverse=True)   # newest first, fixed order
    for r in rows[:n]:
        tests = json.loads(r["public_test_cases"]) + _private_tests(r["private_test_cases"])
        prompt = (f"{r['question_content']}\n\n"
                  "Write a complete Python 3 program that reads from standard input and writes to standard output. "
                  "Return only the final program in a single ```python code block.")
        yield dict(id=r["question_id"], title=r["question_title"], date=r["contest_date"], tests=tests, prompt=prompt)


# ------------------------------------------------------------------ scoring

def boxed(text):
    m = re.findall(r"\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", text)
    if not m:
        return None
    s = re.sub(r"[^0-9\-]", "", m[-1])
    try:
        return int(s)
    except ValueError:
        return None


def code_block(text):
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    return m[-1] if m else None


def _limits():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    os.setsid()


def run_tests(code, tests, per_test_s=10):
    d = tempfile.mkdtemp(prefix="lrr-lcb-", dir=SCRATCH)
    path = os.path.join(d, "sol.py")
    open(path, "w").write(code)
    passed = 0
    for t in tests:
        try:
            p = subprocess.run([sys.executable, "-I", path], input=t["input"], capture_output=True, text=True,
                               timeout=per_test_s, cwd=d, preexec_fn=_limits, env={"PATH": "/usr/bin:/bin"})
            got, exp = p.stdout.split(), t["output"].split()
            if p.returncode == 0 and got == exp:
                passed += 1
            else:
                break   # LCB scoring: all tests must pass; stop at first failure
        except subprocess.TimeoutExpired:
            break
    return passed, len(tests)


# ------------------------------------------------------------------ main

def ask(url, prompt, max_tokens, temperature, top_p, top_k):
    t = time.time()
    r = requests.post(f"{url}/v1/chat/completions", json={
        "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
        "temperature": temperature, "top_p": top_p, "top_k": top_k, "seed": 1}, timeout=6 * 3600)
    r.raise_for_status()
    d = r.json()
    m = d["choices"][0]["message"]
    return dict(content=m.get("content") or "", reasoning_chars=len(m.get("reasoning_content") or ""),
                finish=d["choices"][0].get("finish_reason"), usage=d.get("usage"),
                tps=d.get("timings", {}).get("predicted_per_second"), wall_s=time.time() - t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--task", choices=["aime", "lcb"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--only-ids", default="", help="comma-separated item ids (e.g. rerun length-capped items)")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    done = {json.loads(l)["id"] for l in open(a.out)} if os.path.exists(a.out) else set()
    items = aime_items() if a.task == "aime" else lcb_items()
    only = set(filter(None, a.only_ids.split(",")))
    for it in items:
        if only and it["id"] not in only:
            continue
        if it["id"] in done:
            continue
        r = ask(a.url, it["prompt"], a.max_tokens, a.temperature, a.top_p, a.top_k)
        rec = dict(id=it["id"], **{k: v for k, v in r.items() if k != "content"}, answer_tail=r["content"][-3000:])
        if a.task == "aime":
            rec.update(expected=it["answer"], got=boxed(r["content"]))
            rec["ok"] = rec["got"] == rec["expected"]
        else:
            code = code_block(r["content"])
            passed, total = run_tests(code, it["tests"]) if code else (0, len(it["tests"]))
            rec.update(title=it["title"], date=it["date"], has_code=bool(code), passed=passed, total=total, ok=passed == total)
        open(a.out, "a").write(json.dumps(rec) + "\n")
        print(f"{rec['id']}: ok={rec['ok']} finish={rec['finish']} toks={(rec['usage'] or {}).get('completion_tokens')} "
              f"tps={rec['tps'] and round(rec['tps'], 1)} wall={rec['wall_s']:.0f}s", flush=True)
    rows = [json.loads(l) for l in open(a.out)]
    print(f"SUMMARY {a.task}: {sum(r['ok'] for r in rows)}/{len(rows)}")


if __name__ == "__main__":
    main()
