#!/usr/bin/env python3
"""Engine-neutral speed probe over the OpenAI chat API (streaming).
Same ~4K-token code prompt and 1024-token generation as speed.py, 3 repeats.
Prefill ~= time to first streamed token; decode = generated tokens / (end - first token).
  speed_openai.py --url http://127.0.0.1:8091 --label strata-gptq --out results/raw/speed/strata-gptq.json
"""
import argparse, json, os, statistics, time
import requests

SRC = os.path.expanduser("~/llama.cpp-lrr/src/llama-model.cpp")


def one(url, model, prompt, n, seed):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": n, "temperature": 0.6,
            "top_p": 0.95, "seed": seed, "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}, "ignore_eos": True}
    t0 = time.time(); first = None; chunks = 0; usage = None
    with requests.post(f"{url}/v1/chat/completions", json=body, stream=True, timeout=3600) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:") or line.strip() == "data: [DONE]":
                continue
            ev = json.loads(line[5:])
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices", []):
                d = ch.get("delta", {})
                if d.get("content") or d.get("reasoning_content"):
                    chunks += 1
                    if first is None:
                        first = time.time()
    t1 = time.time()
    out_toks = (usage or {}).get("completion_tokens") or chunks
    return dict(prompt_tokens=(usage or {}).get("prompt_tokens"), ttft_s=round(first - t0, 2),
                tg_n=out_toks, tg_tps=round(out_toks / max(t1 - first, 1e-6), 1),
                pp_tps=round(((usage or {}).get("prompt_tokens") or 0) / max(first - t0, 1e-6)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--label", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=""); ap.add_argument("--n", type=int, default=1024); ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    model = a.model or requests.get(f"{a.url}/v1/models").json()["data"][0]["id"]
    prompt = "Explain, step by step, what this C++ code does and list any bugs you see.\n\n" + open(SRC, errors="replace").read()[:14000]
    runs = [one(a.url, model, prompt, a.n, 7 + i) for i in range(a.reps)]
    for r in runs:
        print(json.dumps(r), flush=True)
    s = dict(label=a.label, runs=runs, pp_tps_median=statistics.median(r["pp_tps"] for r in runs),
             tg_tps_median=statistics.median(r["tg_tps"] for r in runs), ttft_median=statistics.median(r["ttft_s"] for r in runs))
    os.makedirs(os.path.dirname(a.out), exist_ok=True); json.dump(s, open(a.out, "w"), indent=1)
    print(f"SPEED {a.label}: prompt {runs[0]['prompt_tokens']} tok, prefill ~{s['pp_tps_median']} tok/s (TTFT {s['ttft_median']} s), decode {s['tg_tps_median']} tok/s")


if __name__ == "__main__":
    main()
