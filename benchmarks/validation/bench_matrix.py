"""Phase 1 baseline matrix: sizes x reps, 512 output tokens, thinking off, varied prompts, one request at a time.

usage: bench_matrix.py OUTDIR [--sizes 4096,32768,...] [--reps 3] [--max-tokens 512] [--seed-base 1000]
Writes OUTDIR/raw-results.jsonl and OUTDIR/telemetry/<label>.csv; stops on any safety abort.
"""
import argparse, json, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness as H

TASK = ("Task: write a long, detailed, multi-section technical report about the documents above. "
        "Cover every document in order, quote specific details, and do not stop early.")

ap = argparse.ArgumentParser()
ap.add_argument("outdir")
ap.add_argument("--sizes", default="4096,32768,65536,131072,163840,196608,204800,229376,262144")
ap.add_argument("--reps", type=int, default=3)
ap.add_argument("--max-tokens", type=int, default=512)
ap.add_argument("--seed-base", type=int, default=1000)
ap.add_argument("--pause", type=float, default=5.0)
a = ap.parse_args()

out = Path(a.outdir)
(out / "telemetry").mkdir(parents=True, exist_ok=True)
results = out / "raw-results.jsonl"
P = H.Prompter()
corpus = H.load_corpus(seed=a.seed_base)
print(f"corpus: {len(corpus)} documents", flush=True)

for size in [int(s) for s in a.sizes.split(",")]:
    for rep in range(a.reps):
        seed = a.seed_base + size // 1024 * 10 + rep
        label = f"{size // 1024}k_r{rep + 1}"
        msgs, local_count = H.build_messages(P, size, corpus, seed, TASK, thinking=False)
        if not H.preflight(wait_s=300):
            print("server busy for 5 min, stopping", flush=True)
            sys.exit(2)
        n_before = H.requests_total()
        sampler = H.Sampler(out / "telemetry" / f"{label}.csv")
        sampler.start()
        time.sleep(2)  # idle lead-in
        res = H.stream_chat(msgs, a.max_tokens, thinking=False, seed=seed, abort_evt=sampler.abort_evt)
        time.sleep(2)
        sampler.stop_evt.set()
        sampler.join()
        n_after = H.requests_total()
        rec = H.last_request_record() or {}
        usage = res.get("usage") or {}
        out_toks = usage.get("completion_tokens") or rec.get("output_tokens")
        client_decode = None
        if res["ttft_s"] and res.get("t_last") and out_toks and out_toks > 1:
            span = res["t_last"] - (res["t_send"] + res["ttft_s"])
            client_decode = round((out_toks - 1) / span, 2) if span > 0 else None
        row = {
            "label": label, "target_tokens": size, "rep": rep + 1, "seed": seed,
            "local_prompt_tokens": local_count,
            "server_prompt_tokens": usage.get("prompt_tokens") or rec.get("prompt_tokens"),
            "output_tokens": out_toks, "finish": res["finish"] or rec.get("finish"),
            "ttft_s": round(res["ttft_s"], 3) if res["ttft_s"] else None,
            "total_s": round(res["total_s"], 3),
            "prefill_tok_s_server": round(rec["prompt_total"] / (rec["prompt_ms"] / 1000), 1)
            if rec.get("prompt_ms") else None,
            "prompt_ms": rec.get("prompt_ms"), "decode_ms": rec.get("decode_ms"),
            "decode_tok_s_server": rec.get("decode_tok_s"), "decode_tok_s_client": client_decode,
            "reused": rec.get("reused"), "expert_hit_rate": rec.get("hit_rate"), "pcie_share": rec.get("pcie_share"),
            "drafts_offered": rec.get("drafts_offered"), "drafts_accepted": rec.get("drafts_accepted"),
            "reasoning_recoveries": rec.get("reasoning_recoveries"),
            "server_request_id": rec.get("id"), "foreign_requests": (n_after - n_before - 1)
            if None not in (n_after, n_before) else None,
            "http_status": res["http_status"], "error": res["error"], "cancelled": res["cancelled"],
            "abort_reason": sampler.abort_reason,
            **H.Sampler.peaks(sampler.rows),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(results, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"{label}: prompt {row['server_prompt_tokens']} (local {local_count}) "
              f"ttft {row['ttft_s']}s prefill {row['prefill_tok_s_server']} tok/s "
              f"decode {row['decode_tok_s_server']} tok/s out {out_toks} reused {row['reused']} "
              f"vram {row['g0_mem_mib_peak']} temp {row['g0_temp_peak']} err {row['error']}", flush=True)
        if sampler.abort_reason or row["error"]:
            print("STOPPING:", sampler.abort_reason or row["error"], flush=True)
            sys.exit(3)
        time.sleep(a.pause)
print("matrix complete", flush=True)
