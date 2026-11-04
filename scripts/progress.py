#!/usr/bin/env python3
"""Snapshot of project progress for the live progress artifact (pushed into its db as progress/current)."""
import glob, json, os, re, subprocess, time, datetime as dt
os.chdir(os.path.expanduser("~/local-reasoning-research"))
R = "results/raw"


def jl(path):
    try:
        return [json.loads(l) for l in open(path)]
    except FileNotFoundError:
        return []


def running(pattern):
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def current_local():
    log = open(f"{R}/logs/queue_quality.log").read() if os.path.exists(f"{R}/logs/queue_quality.log") else ""
    m = re.findall(r"^== (\S+) (\S+) ", log, re.M)
    return m[-1] if m else None


QUEUES = []
cur = current_local()
for label, model in (("super-nvfp4", "Nemotron 3.5 Super (NVFP4)"), ("qwen38fn-q4", "Qwen3.8-Flash-Next (Q4)"), ("bolt-iq2", "Nemotron 3.5 Bolt (IQ2)")):
    for task, total in (("aime", 15), ("lcb", 10)):
        rows = jl(f"{R}/quality/{label}/{task}.jsonl")
        active = cur == (label, task) and running("queue_quality.sh")
        QUEUES.append(dict(group="Local quality (RTX PRO 4000)", model=model, task="AIME 2026" if task == "aime" else "LiveCodeBench v6 hard",
                           done=len(rows), total=total, correct=sum(r["ok"] for r in rows),
                           length_capped=sum(r.get("finish") == "length" for r in rows),
                           status="running" if active else ("done" if len(rows) >= total else "queued"),
                           last_s=round(rows[-1]["wall_s"]) if rows else None))
for d, model, pat in (("opus-5-5", "Claude Opus 5.5 (subscription)", "queue_cloud.sh opus"), ("minimax-m3", "MiniMax-M3 (subscription)", "queue_cloud.sh minimax")):
    alive = running(pat)
    for task, total in (("aime", 15), ("lcb", 10)):
        rows = jl(f"{R}/quality/{d}/{task}.jsonl")
        st = "done" if len(rows) >= total else ("running" if alive else "stopped")
        QUEUES.append(dict(group="Cloud reference", model=model, task="AIME 2026" if task == "aime" else "LiveCodeBench v6 hard",
                           done=len(rows), total=total, correct=sum(r["ok"] for r in rows), length_capped=0, status=st,
                           last_s=round(rows[-1]["wall_s"]) if rows else None))
    lc = sorted(glob.glob(f"{R}/cloud/{d}/v2_262144_s*.json"))
    QUEUES.append(dict(group="Cloud reference", model=model, task="Long context 262K (v2 prompts)", done=len(lc), total=3,
                       correct=sum(json.load(open(f))["scores"]["_score"] == 1.0 for f in lc), length_capped=0,
                       status="done" if len(lc) >= 3 else ("running" if alive else "stopped"), last_s=None))

# Phase 2: 64K coding reruns of capped items + 10-run stability suite
P2 = running("queue_phase3.sh") or running("queue_super1m.sh")
p2log = open(f"{R}/logs/queue_phase3.log").read() if os.path.exists(f"{R}/logs/queue_phase3.log") else ""
p2cur = (re.findall(r"^== (\S+) (\S+) ", p2log, re.M) or [None])[-1]
for label, model, n in (("qwen38fn-q4", "Qwen3.8-Flash-Next (Q4)", 1),):
    rows = jl(f"{R}/quality/{label}/lcb64k.jsonl")
    st = "done" if len(rows) >= n else ("running" if P2 and p2cur == (label, "lcb64k") else ("queued" if P2 else "stopped"))
    QUEUES.append(dict(group="Coding reruns at 64K (dropped after MiniMax went 0/4; only 1 Qwen item run)", model=model, task="LiveCodeBench capped items",
                       done=len(rows), total=n, correct=sum(r["ok"] for r in rows), length_capped=sum(r.get("finish") == "length" for r in rows),
                       status=st, last_s=None))
rows = jl(f"{R}/quality/minimax-m3/lcb64k.jsonl")
QUEUES.append(dict(group="Coding reruns at 64K (dropped after MiniMax went 0/4; only 1 Qwen item run)", model="MiniMax-M3 (subscription)", task="LiveCodeBench capped items",
                   done=len(rows), total=4, correct=sum(r["ok"] for r in rows), length_capped=0,
                   status="done" if len(rows) >= 4 else ("running" if running("lcb64k") else "stopped"), last_s=None))
stab = sorted(glob.glob(f"{R}/STABILITY-v2-*/*_s*_*[0-9].json"))
st_ok = sum(json.load(open(f))["scores"]["_score"] == 1.0 for f in stab)
QUEUES.append(dict(group="Phase 2: 256K stability qualification (brief 4.4)", model="Qwen3.8-Flash-Next (Q4, YaRN x2)",
                   task="10 consecutive runs, >=262,144 input tokens", done=len(stab), total=10, correct=st_ok, length_capped=0,
                   status="done" if len(stab) >= 10 else ("running" if P2 and p2cur and p2cur[0] == "qwen" else ("queued" if P2 else "stopped")), last_s=None))

for label, model, tok, n in (("qwen38fn-q4-yarn4-544k-q8kv", "Qwen3.8-Flash-Next (YaRN x4, q8 KV)", "512K", 2),
                             ("super-nvfp4-1m-q8kv", "Nemotron 3.5 Super (native 1M, q8 KV)", "512K + 1M", 2)):
    fs = sorted(glob.glob(f"{R}/{label}/*_s*_*[0-9].json"))
    QUEUES.append(dict(group="Context extension (512K / 1M)", model=model, task=f"{tok} long-context runs", done=len(fs), total=n,
                       correct=sum(json.load(open(f))["scores"]["_score"] == 1.0 for f in fs), length_capped=0,
                       status="done" if len(fs) >= n else ("running" if (label.startswith("super") and running("queue_super1m.sh")) or (P2 and p2cur and label.startswith(p2cur[0][:5])) else ("queued" if P2 else "stopped")), last_s=None))

# Qwen focus phase
FQ = running("queue_qwen_focus.sh")
for label, task, n, pat in (("CANON-qwen38fn-q4-288k", "Q4: 3 shared 262K prompts (same as Opus/MiniMax)", 3, "v2_*.json"),
                            ("CANON-qwen38fn-iq3s-288k", "3-bit IQ3_S: same 3 shared 262K prompts", 3, "v2_*.json")):
    fs = sorted(f for f in glob.glob(f"{R}/{label}/{pat}") if "monitor" not in f)
    QUEUES.append(dict(group="Qwen focus: quantization + same-prompt comparison", model="Qwen3.8-Flash-Next", task=task, done=len(fs), total=n,
                       correct=sum(json.load(open(f))["scores"]["_score"] == 1.0 for f in fs), length_capped=0,
                       status="done" if len(fs) >= n else ("running" if FQ else "stopped"), last_s=None))
rows = jl(f"{R}/quality/qwen38fn-iq3s/aime.jsonl")
QUEUES.append(dict(group="Qwen focus: quantization + same-prompt comparison", model="Qwen3.8-Flash-Next", task="3-bit IQ3_S: AIME 2026 (Q4 scored 14/15)",
                   done=len(rows), total=15, correct=sum(r["ok"] for r in rows), length_capped=sum(r.get("finish") == "length" for r in rows),
                   status="done" if len(rows) >= 15 else ("running" if FQ else "stopped"), last_s=None))
sp = sorted(glob.glob(f"{R}/speed/*.json"))
QUEUES.append(dict(group="Qwen focus: speed options", model="Qwen3.8-Flash-Next", task="baseline / MTP drafting / 3-bit (GPU-expert option dropped: OOM)",
                   done=len(sp), total=3, correct=len(sp), length_capped=0, status="done" if len(sp) >= 3 else ("running" if FQ else "stopped"), last_s=None))

ag = sorted(glob.glob(f"{R}/agentic/*.json"))
QUEUES.append(dict(group="Claude Code integration (agentic, local model)", model="Qwen3.8-Flash-Next (Q4) via Claude Code",
                   task="easy task (2 bugs, hinted) x3 + hard task (3 bugs, no hints) x3", done=len(ag), total=6,
                   correct=sum(json.load(open(f)).get("tests_pass") and json.load(open(f)).get("tests_untouched") for f in ag), length_capped=0,
                   status="done" if len(ag) >= 6 else ("running" if running("queue_agentic.sh") else "stopped"), last_s=None))

# waiting on a usage-limit reset?
waiting = None
lp = f"{R}/logs/queue_cloud_opus.log"
if os.path.exists(lp):
    w = [l for l in open(lp) if "[usage-limit]" in l]
    if w and running("queue_cloud.sh opus"):
        waiting = w[-1].strip()[:200]

LONG = []
for f in sorted(glob.glob(f"{R}/*/*_s*_*[0-9].json")):
    if "/quality/" in f: continue
    d = json.load(open(f)); s = d["scores"]
    n = sum(1 for k in s if not k.startswith("_"))
    LONG.append(dict(model=d["label"], tokens=d["prompt_tokens_server"], seed=d["seed"], suite=d.get("suite", "easy"),
                     score=sum(v["ok"] for k, v in s.items() if not k.startswith("_")), of=n,
                     prefill_min=round(d["prefill_s"] / 60, 1), gen_tps=round(d["gen_tps"] or 0, 1)))
for f in sorted(glob.glob(f"{R}/cloud/*/*.json")):
    d = json.load(open(f)); s = d["scores"]
    LONG.append(dict(model=d["backend"] + (" (v2)" if "v2_" in f else ""), tokens=d.get("usage", {}).get("input"), seed=d["seed"],
                     suite=d.get("suite"), score=sum(v["ok"] for k, v in s.items() if not k.startswith("_")),
                     of=sum(1 for k in s if not k.startswith("_")), prefill_min=None, gen_tps=None))

PHASES = [
    ("Environment discovery", "done"), ("Model research & HGA", "done"), ("Candidate triage", "done"),
    ("Hardware feasibility", "done"), ("Benchmark harness", "done"),
    ("256K qualification runs (64K→128K→256K)", "done"), ("Quality suite: AIME + coding", "done"),
    ("Cloud comparison (Opus, MiniMax)", "done"), ("Coding reruns at 64K budget", "done"), ("10-run 256K stability suite", "done"),
    ("512K / 1M extension", "done"), ("Qwen focus: speed + 3-bit quantization", "done"),
    ("Fine-tuning assessment", "done"), ("Deployment + Claude Code integration", "done"), ("Final report", "done"),
]

snap = dict(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            gpu=subprocess.run(["nvidia-smi", "-i", "GPU-4e9ed5ea-d6d0-183f-9335-fd87f65d3f16",
                                "--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True).stdout.strip(),
            queues=QUEUES, longctx=LONG, phases=[dict(name=n, status=s) for n, s in PHASES], waiting=waiting)
out = "/tmp/claude-1000/-home-adam/aee8f88e-e0a7-4d76-9aed-0c7c432b0b53/scratchpad/progress.json"
json.dump(snap, open(out, "w"))
print(out, sum(q["done"] for q in QUEUES), "/", sum(q["total"] for q in QUEUES))
