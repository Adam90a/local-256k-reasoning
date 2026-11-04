#!/usr/bin/env python3
"""Long-context test for engines with only an OpenAI/Anthropic API (Strata). Same prompts, seeds and scorer as longctx.py.
Prompt sized with the server's Anthropic count_tokens minus its fixed overhead (measured on a tiny message); the
server's own usage.prompt_tokens on the real request is the number reported (must be >= target).
  longctx_openai.py --url http://127.0.0.1:8091 --tokens 262144 --seed 101 --out x.json
"""
import argparse, json, os, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import longctx as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--tokens", type=int, required=True); ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--suite", default="both"); ap.add_argument("--max-new", type=int, default=32768); ap.add_argument("--label", default="")
    ap.add_argument("--out", required=True); ap.add_argument("--margin", type=int, default=128)
    a = ap.parse_args()
    model = requests.get(f"{a.url}/v1/models").json()["data"][0]["id"]

    def anth_count(msgs):
        sysm = next(m["content"] for m in msgs if m["role"] == "system")
        rest = [m for m in msgs if m["role"] != "system"]
        return requests.post(f"{a.url}/v1/messages/count_tokens", json={"model": model, "system": sysm, "messages": rest}, timeout=600).json()["input_tokens"]

    probe = [{"role": "system", "content": "You are a test."}, {"role": "user", "content": "Hello there, how are you today?"}]
    real = requests.post(f"{a.url}/v1/chat/completions", json={"model": model, "messages": probe, "max_tokens": 1}).json()["usage"]["prompt_tokens"]
    offset = anth_count(probe) - real
    counter = lambda msgs: anth_count(msgs) - offset
    t0 = time.time()
    p = L.build_prompt(a.url, a.tokens + a.margin, a.seed, a.suite, counter=counter)
    print(f"[build] est_tokens={p['prompt_tokens']} (count_tokens offset {offset}) ({time.time()-t0:.0f}s)", flush=True)

    body = {"model": model, "messages": p["messages"], "max_tokens": a.max_new, "temperature": 0.6, "top_p": 0.95, "top_k": 20,
            "seed": a.seed, "stream": True, "stream_options": {"include_usage": True}}
    t1 = time.time(); first = None; content = []; reasoning = 0; usage = None; finish = None
    with requests.post(f"{a.url}/v1/chat/completions", json=body, stream=True, timeout=24 * 3600) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:") or line.strip() == "data: [DONE]":
                continue
            ev = json.loads(line[5:])
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices", []):
                d = ch.get("delta", {}); finish = ch.get("finish_reason") or finish
                if d.get("content") or d.get("reasoning_content"):
                    if first is None:
                        first = time.time()
                    content.append(d.get("content") or ""); reasoning += len(d.get("reasoning_content") or "")
    t2 = time.time()
    text = "".join(content); u = usage or {}
    gen = u.get("completion_tokens") or 0
    res = dict(label=a.label, engine="strata", suite=a.suite, seed=a.seed, target_tokens=a.tokens,
               prompt_tokens_server=u.get("prompt_tokens"), prompt_tokens_counted=p["prompt_tokens"],
               meets_target=(u.get("prompt_tokens") or 0) >= a.tokens, output_tokens=gen, finish=finish,
               truncated=finish == "length", prefill_s=round(first - t1, 1) if first else None,
               prefill_tps=round((u.get("prompt_tokens") or 0) / max(first - t1, 1e-6)) if first else None,
               gen_tps=round(gen / max(t2 - first, 1e-6), 1) if first else None, wall_s=round(t2 - t1),
               reasoning_chars=reasoning, expected=p["expected"])
    res["scores"] = L.score(text, p["expected"]); res["answer_tail"] = text[-4000:]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True); json.dump(res, open(a.out, "w"), indent=1, default=str)
    s = res["scores"]
    print(f"[done] score={s['_score']:.2f} hard={s['_score_hard']} json={s['_json_ok']} prompt_n={res['prompt_tokens_server']} "
          f"meets_target={res['meets_target']} finish={finish} prefill={res['prefill_s']}s ({res['prefill_tps']} tok/s) "
          f"gen={gen} tok @ {res['gen_tps']}", flush=True)
    for k, v in s.items():
        if not k.startswith("_") and not v["ok"]:
            print(f"   BAD {k}: expected={v['expected']} got={v['got']}")


if __name__ == "__main__":
    main()
