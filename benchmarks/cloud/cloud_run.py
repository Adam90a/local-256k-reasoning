#!/usr/bin/env python3
"""Run the same tasks on cloud reference models, scored with the same scorers.

Backends (both subscription-billed, $0 API spend — see research/resource-budget.md):
  opus     : `claude -p` on Adam's Claude subscription (claude.ai auth). MCP/tools/slash commands
             disabled so only our system prompt (~0.6K overhead) is added. --effort high.
  minimax  : MiniMax-M3 via api.minimax.io/anthropic with MINIMAX_API_KEY (subscription key).

  cloud_run.py --backend opus --task longctx --prompt-file results/prompts/262144_s11.json --out results/raw/cloud/opus/...json
  cloud_run.py --backend minimax --task aime --out results/raw/quality/minimax-m3/aime.jsonl
"""
import argparse, json, os, re, subprocess, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "context"))
sys.path.insert(0, os.path.join(HERE, "..", "reasoning"))

OPUS_MODEL = "claude-opus-5-5"
MINIMAX_MODEL = "MiniMax-M3"


def minimax_key():
    k = os.environ.get("MINIMAX_API_KEY")
    if not k:
        for f in ("~/.bashrc", "~/.hermes/.env"):
            for line in open(os.path.expanduser(f), errors="ignore"):
                m = re.match(r"\s*(?:export\s+)?MINIMAX_API_KEY=[\"']?([^\"'\s]+)", line)
                if m:
                    k = m.group(1); break
            if k:
                break
    if not k or not k.startswith("sk-cp-"):
        raise SystemExit("MINIMAX_API_KEY missing or not a subscription (sk-cp-) key; refusing (subscription only).")
    return k


def wait_for_reset(msg):
    """Adam: on a usage limit, wait and continue automatically. Parse 'resets 8pm (America/New_York)' or
    'resets 7:30pm (...)'; sleep until 3 min after it. Unparseable -> retry in 30 min."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    m = re.search(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]+)\))?", msg, re.I)
    secs = 1800
    if m:
        h, mi, ap, tz = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower(), m.group(4) or "America/New_York"
        if ap == "pm" and h != 12: h += 12
        if ap == "am" and h == 12: h = 0
        try:
            now = dt.datetime.now(ZoneInfo(tz))
            t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if t <= now:
                t += dt.timedelta(days=1)
            secs = (t - now).total_seconds() + 180
        except Exception:
            pass
    print(f"[usage-limit] {msg!r} -> sleeping {secs/60:.0f} min, then retrying", flush=True)
    time.sleep(secs)


def call(backend, system, user, max_tokens):
    t = time.time()
    if backend == "opus":
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"
        cmd = ["claude", "-p", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "",
               "--disable-slash-commands", "--no-session-persistence", "--model", OPUS_MODEL, "--effort", "high",
               "--output-format", "json", "--system-prompt", system or "You are a careful assistant."]
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, env=env, timeout=4 * 3600,
                           cwd=os.environ.get("LRR_SCRATCH", "/tmp"))
        d = json.loads(p.stdout)
        if d.get("is_error"):
            msg = str(d.get("result"))
            if "limit" in msg.lower():
                wait_for_reset(msg)
                return call(backend, system, user, max_tokens)   # retry the same item after the reset
            raise RuntimeError(msg)
        mu = d.get("modelUsage", {}).get(OPUS_MODEL, {})
        return dict(content=d.get("result") or "", wall_s=time.time() - t, model=OPUS_MODEL,
                    usage=dict(input=mu.get("inputTokens", 0) + mu.get("cacheCreationInputTokens", 0) + mu.get("cacheReadInputTokens", 0),
                               output=mu.get("outputTokens"), thinking=mu.get("thinkingTokens")),
                    list_price_usd_not_billed=d.get("total_cost_usd"))
    else:
        body = dict(model=MINIMAX_MODEL, max_tokens=max_tokens, messages=[{"role": "user", "content": user}],
                    thinking={"type": "enabled", "budget_tokens": max(1024, max_tokens - 4096)})
        if system:
            body["system"] = system
        body["stream"] = True
        for attempt in range(5):
            # Stream (SSE) so long thinking keeps the connection active; 300 s of silence = stalled -> retry.
            text, thinking, usage, model, stop = [], [], {}, None, None
            try:
                with requests.post("https://api.minimax.io/anthropic/v1/messages", timeout=(30, 300), json=body, stream=True,
                                   headers={"x-api-key": minimax_key(), "anthropic-version": "2023-06-01"}) as r:
                    if r.status_code in (429, 500, 502, 503, 529):
                        time.sleep(30 * (attempt + 1)); continue
                    r.raise_for_status()
                    for line in r.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        ev = json.loads(line[5:].strip())
                        typ = ev.get("type")
                        if typ == "message_start":
                            model = ev["message"].get("model"); usage.update(ev["message"].get("usage") or {})
                        elif typ == "content_block_delta":
                            dl = ev.get("delta", {})
                            if dl.get("type") == "text_delta": text.append(dl.get("text", ""))
                            elif dl.get("type") == "thinking_delta": thinking.append(dl.get("thinking", ""))
                        elif typ == "message_delta":
                            stop = ev.get("delta", {}).get("stop_reason") or stop; usage.update(ev.get("usage") or {})
                        elif typ == "error":
                            raise RuntimeError(str(ev.get("error")))
                break
            except (requests.exceptions.RequestException, RuntimeError, json.JSONDecodeError) as e:
                print(f"[minimax] request failed ({type(e).__name__}: {str(e)[:120]}); retry {attempt + 1}/5", flush=True)
                time.sleep(30)
        else:
            raise RuntimeError("minimax: 5 failed attempts")
        return dict(content="".join(text), wall_s=time.time() - t, model=model,
                    usage=dict(input=usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0), output=usage.get("output_tokens")),
                    stop=stop, thinking_chars=len("".join(thinking)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["opus", "minimax"], required=True)
    ap.add_argument("--task", choices=["longctx", "aime", "lcb"], required=True)
    ap.add_argument("--prompt-file", help="longctx prompt saved by longctx.py --save-prompt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--only-ids", default="")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    if a.task == "longctx":
        from longctx import score
        pf = json.load(open(a.prompt_file))
        sysmsg = next(m["content"] for m in pf["messages"] if m["role"] == "system")
        usr = next(m["content"] for m in pf["messages"] if m["role"] == "user")
        r = call(a.backend, sysmsg, usr, a.max_tokens)
        res = dict(backend=a.backend, prompt_file=a.prompt_file, seed=pf["seed"], suite=pf["suite"],
                   prompt_tokens_builder=pf["prompt_tokens_builder"], expected=pf["expected"],
                   **{k: v for k, v in r.items() if k != "content"}, answer_tail=r["content"][-4000:])
        res["scores"] = score(r["content"], pf["expected"])
        json.dump(res, open(a.out, "w"), indent=1, default=str)
        s = res["scores"]
        print(f"[{a.backend}] score={s['_score']:.2f} easy={s['_score_easy']} hard={s['_score_hard']} "
              f"in={r['usage']['input']} out={r['usage']['output']} wall={r['wall_s']:.0f}s")
        for k, v in s.items():
            if not k.startswith("_") and not v["ok"]:
                print(f"   BAD {k}: expected={v['expected']} got={v['got']}")
        return

    import quality as q
    done = {json.loads(l)["id"] for l in open(a.out)} if os.path.exists(a.out) else set()
    items = q.aime_items() if a.task == "aime" else q.lcb_items()
    only = set(filter(None, a.only_ids.split(",")))
    for it in items:
        if only and it["id"] not in only:
            continue
        if it["id"] in done:
            continue
        r = call(a.backend, None, it["prompt"], a.max_tokens)
        rec = dict(id=it["id"], backend=a.backend, **{k: v for k, v in r.items() if k != "content"}, answer_tail=r["content"][-3000:])
        if a.task == "aime":
            rec.update(expected=it["answer"], got=q.boxed(r["content"]))
            rec["ok"] = rec["got"] == rec["expected"]
        else:
            code = q.code_block(r["content"])
            passed, total = q.run_tests(code, it["tests"]) if code else (0, len(it["tests"]))
            rec.update(title=it["title"], has_code=bool(code), passed=passed, total=total, ok=passed == total)
        open(a.out, "a").write(json.dumps(rec, default=str) + "\n")
        print(f"{rec['id']}: ok={rec['ok']} out={r['usage'].get('output')} wall={r['wall_s']:.0f}s", flush=True)
    rows = [json.loads(l) for l in open(a.out)]
    print(f"SUMMARY {a.backend} {a.task}: {sum(r['ok'] for r in rows)}/{len(rows)}")


if __name__ == "__main__":
    main()
