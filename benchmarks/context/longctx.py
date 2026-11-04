#!/usr/bin/env python3
"""Long-context qualification test (brief §4.3 Gate C / §4.4).

Builds one prompt of an exact target token length from real source code, plants
facts at chosen depths, and asks a fixed battery of questions answered as JSON.
Token counts come from the server's own tokenizer after the chat template is
applied, so template overhead is included. Scoring is automatic.

Usage:
  longctx.py --url http://127.0.0.1:8090 --tokens 262144 --seed 1 --out results/raw/x.json
"""
import argparse, json, os, random, re, string, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = [os.path.expanduser("~/llama.cpp-lrr"),
           *sorted(__import__("glob").glob(os.path.expanduser("~/vllm-env/lib/python3*/site-packages/vllm")))]
EXTS = (".c", ".cpp", ".h", ".cu", ".py")

SYSTEM = ("You are auditing a large codebase dump. Read everything carefully. "
          "Standing rule: your final answer must be a single JSON object and the "
          "JSON must contain the key \"ack\" with the value \"{ack}\".")

# ---------------------------------------------------------------- haystack

def code_files(seed):
    files = []
    for root in SOURCES:
        for dp, _, fns in os.walk(root):
            if "/.git" in dp or "/build" in dp:
                continue
            for fn in fns:
                if fn.endswith(EXTS):
                    files.append(os.path.join(dp, fn))
    files.sort()
    random.Random(seed).shuffle(files)
    return files


def rand_id(rng, n=6):
    return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def make_facts(rng):
    """Planted facts. Each: (depth 0..1, text, question-key, expected answer)."""
    f = {}
    # 1-3: single needles at start / middle / end (exact strings)
    for key, depth in (("needle_start", 0.03), ("needle_mid", 0.5), ("needle_end", 0.96)):
        name, code = rand_id(rng, 4), f"{rng.randint(10000, 99999)}-{rand_id(rng, 2)}"
        f[key] = dict(depth=depth, ask=f"What is the vault access code for vault {name}?", expect=code,
                      text=f"# NOTE(ops): the vault access code for vault {name} is {code}. Do not rotate it.\n")
    # 4: distractors — 6 similar keys spread out, ask one
    target = rng.randrange(6)
    hosts = [f"db-{rand_id(rng, 3).lower()}" for _ in range(6)]
    ports = rng.sample(range(20000, 60000), 6)
    for i in range(6):
        f[f"_distractor_{i}"] = dict(depth=0.1 + 0.13 * i,
                                     text=f"# CONFIG: replica host {hosts[i]} listens on port {ports[i]}.\n")
    f["distractor"] = dict(depth=None, ask=f"Which port does replica host {hosts[target]} listen on? Answer with the number.",
                           expect=str(ports[target]))
    # 5: multi-hop chain across distance (A at 12%, B at 58%, C at 88%)
    svc, lib, ver, ticket = f"svc-{rand_id(rng,3).lower()}", f"lib{rand_id(rng,4).lower()}", f"{rng.randint(2,9)}.{rng.randint(0,9)}.{rng.randint(0,9)}", f"SEC-{rng.randint(1000,9999)}"
    f["_hop1"] = dict(depth=0.12, text=f"# DEPENDENCY: service {svc} links against {lib} for request parsing.\n")
    f["_hop2"] = dict(depth=0.58, text=f"# PIN: {lib} is pinned to version {ver} in the production lockfile.\n")
    f["_hop3"] = dict(depth=0.88, text=f"# ADVISORY: {lib} version {ver} is affected by advisory {ticket}.\n")
    f["multihop"] = dict(depth=None, ask=f"Which security advisory affects service {svc} through its dependencies? Answer with the advisory id.",
                         expect=ticket)
    # 6: contradiction detection — same setting, two values, far apart
    setting = f"MAX_{rand_id(rng,4)}_RETRIES"
    a, b = rng.sample(range(2, 30), 2)
    f["_contra1"] = dict(depth=0.22, text=f"# POLICY: {setting} must be exactly {a} in all environments.\n")
    f["_contra2"] = dict(depth=0.81, text=f"# POLICY: {setting} must be exactly {b} in all environments.\n")
    f["contradiction"] = dict(depth=None, ask=f"Two POLICY comments contradict each other about {setting}. List both values as [smaller, larger].",
                              expect=sorted([a, b]))
    # 7: counting across the whole context
    tag = f"TODO-{rand_id(rng,3)}"
    n = rng.randint(3, 7)
    for i in range(n):
        f[f"_count{i}"] = dict(depth=0.05 + 0.9 * (i + 0.5) / n, text=f"# {tag}: follow-up item {i+1} pending review.\n")
    f["count"] = dict(depth=None, ask=f"How many comments tagged {tag} appear in the dump? Answer with a number.", expect=n)
    return f


def make_hard_facts(rng):
    """Reasoning across distant facts (not lookup). Link order is shuffled across depths."""
    import datetime as dt
    f = {}
    # H1: variable chain of 6 hops, links scattered in random depth order, plus 2 decoy chains.
    def chain(prefix, value):
        names = [f"{prefix}_{rand_id(rng, 3).lower()}" for _ in range(6)]
        lines = [f"# SET: {names[0]} = {value}\n"] + [f"# ALIAS: {names[i]} = {names[i-1]}\n" for i in range(1, 6)]
        return names, lines
    val = rng.randint(1000, 9999)
    names, lines = chain("knob", val)
    decoys = [chain("knob", rng.randint(1000, 9999))[1] for _ in range(2)]
    all_lines = lines + decoys[0] + decoys[1]
    depths = sorted(rng.uniform(0.04, 0.95) for _ in all_lines)
    rng.shuffle(all_lines)
    for i, (d, t) in enumerate(zip(depths, all_lines)):
        f[f"_chain{i}"] = dict(depth=d, text=t)
    f["var_chain"] = dict(depth=None, ask=f"Following the SET/ALIAS comments, what integer value does {names[-1]} resolve to?",
                          expect=val)
    # H2: cross-file unit bug (basis points divided by 100 instead of 10000), plus a customer->tier hop.
    tiers = {"gold": rng.randint(20, 45), "silver": rng.randint(50, 80), "basic": rng.randint(85, 140)}
    cust = {f"cust{rand_id(rng,3).lower()}": t for t in tiers for _ in range(1)}
    who, tier = rng.choice(list(cust.items()))
    amount = rng.randint(100000, 9999999)
    f["_bill1"] = dict(depth=rng.uniform(0.08, 0.3), text=(
        "# ---- lrr_billing/rates.py ----\n"
        f"FEE_RATE_BPS = {json.dumps(tiers)}  # fee rate per tier, in basis points (1 bp = 0.01%)\n"))
    f["_bill2"] = dict(depth=rng.uniform(0.4, 0.6), text=(
        "# ---- lrr_billing/fees.py ----\n"
        "def compute_fee(amount_cents, tier):\n"
        "    \"\"\"Fee for a charge, returned in cents.\"\"\"\n"
        "    return round(amount_cents * FEE_RATE_BPS[tier] / 100)\n"))
    f["_bill3"] = dict(depth=rng.uniform(0.7, 0.92), text=(
        "# ---- lrr_billing/customers.py ----\n"
        f"CUSTOMER_TIER = {json.dumps(cust)}\n"))
    f["billing_fee"] = dict(depth=None, ask=(
        f"The lrr_billing module (split across several files in the dump) contains one arithmetic bug. "
        f"After fixing it, what fee in cents is charged to customer {who} for amount_cents={amount}? Integer, rounded to nearest."),
        expect=round(amount * tiers[tier] / 10000))
    # H3: scheduling with scattered constraints; answer = earliest permitted date.
    start = dt.date(2026, 3, 2)  # Monday
    people = ["Ana", "Bram", "Chen", "Dita", "Ezra"]
    rng.shuffle(people)
    roster = {start + dt.timedelta(weeks=w): people[w % 5] for w in range(5)}
    dba = rng.choice(people[1:4])
    freeze_end = start + dt.timedelta(days=rng.randint(3, 10))
    cand = [start + dt.timedelta(days=i) for i in range(35)]
    ok = [d for d in cand if d.weekday() < 4 and d > freeze_end and
          roster[start + dt.timedelta(weeks=(d - start).days // 7)] == dba]
    blackout = ok[0] if len(ok) > 1 and rng.random() < 0.7 else None
    if blackout:
        ok = ok[1:]
    f["_sched_roster"] = dict(depth=rng.uniform(0.05, 0.25), text="".join(
        f"# ONCALL: week starting Monday {d.isoformat()}: {p}\n" for d, p in roster.items()))
    f["_sched_r1"] = dict(depth=rng.uniform(0.3, 0.45), text="# RULE: database migrations never run on Fridays, Saturdays or Sundays.\n")
    f["_sched_r2"] = dict(depth=rng.uniform(0.5, 0.65), text=f"# RULE: the change freeze lasts through {freeze_end.isoformat()} inclusive; no migrations during it.\n")
    f["_sched_r3"] = dict(depth=rng.uniform(0.7, 0.8), text=f"# RULE: a migration may only run on a day when the on-call engineer is {dba} (the only DBA-certified engineer).\n")
    if blackout:
        f["_sched_r4"] = dict(depth=rng.uniform(0.85, 0.95), text=f"# RULE: {blackout.isoformat()} is a datacenter maintenance day; no migrations.\n")
    f["migration_date"] = dict(depth=None, ask="Applying every RULE comment and the ONCALL roster, what is the earliest date a database migration may run? Answer YYYY-MM-DD.",
                               expect=ok[0].isoformat())
    # H4: arithmetic over three distant values.
    rows, shards, rf = rng.randint(2, 9) * 250000, rng.randint(11, 47), rng.choice([2, 3, 5])
    tbl = f"events_{rand_id(rng,3).lower()}"
    f["_cap1"] = dict(depth=rng.uniform(0.1, 0.3), text=f"# CAPACITY: each shard of {tbl} holds {rows:,} rows.\n")
    f["_cap2"] = dict(depth=rng.uniform(0.4, 0.6), text=f"# PLAN: {tbl} is split into {shards} shards.\n")
    f["_cap3"] = dict(depth=rng.uniform(0.7, 0.9), text=f"# PLAN: every shard of {tbl} is replicated with replication factor {rf}.\n")
    f["capacity"] = dict(depth=None, ask=f"How many row copies in total can {tbl} store across all shards and replicas? Answer with an integer.",
                         expect=rows * shards * rf)
    return f


FILE_RE = re.compile(r"\n// ===== FILE: (.*?) =====\n")


def split_files(text):
    parts = FILE_RE.split(text)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def callers_in(text, name):
    """Files (by header path) that call name( as a bare call and do not define it."""
    call = re.compile(r"(?:(?<![\w.])|(?<![\w.])(?!self\.|cls\.)[A-Za-z_]\w*\.)" + re.escape(name) + r"\(")
    defn = re.compile(r"^\s*(?:async\s+)?def\s+" + re.escape(name) + r"\(", re.M)
    out = []
    for p, body in split_files(text).items():
        if defn.search(body):
            continue
        if any(not ln.lstrip().startswith(("#", "//", "import ", "from ")) for ln in body.splitlines() if call.search(ln)):
            out.append(p)
    return sorted(out)


def make_aggregation(hay, rng):
    """Pick a module-level Python function defined exactly once in the first 60% of the haystack, never used as a
    method anywhere (no '.name(' and no indented 'def name('), and bare-called from 3-10 other files there."""
    early = hay[: int(len(hay) * 0.6)]
    files = split_files(early)
    attr_called = set(re.findall(r"(?:self|cls|\)|\])\.([A-Za-z_]\w{7,})\(", hay))  # method-style uses only
    method_defs = set(re.findall(r"^[ \t]+(?:async\s+)?def\s+([A-Za-z_]\w{7,})\(", hay, re.M))
    defs, bare = {}, {}
    for p, body in files.items():
        for name in re.findall(r"^def\s+([A-Za-z_]\w{7,})\(", body, re.M):  # module-level functions only
            defs.setdefault(name, set()).add(p)
        code = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith(("#", "//", "import ", "from ")))
        bare[p] = set(re.findall(r"(?:(?<![\w.])|(?<![\w.])(?!self\.|cls\.)[A-Za-z_]\w*\.)([A-Za-z_]\w{7,})\(", code))
    cands = []
    for name, where in sorted(defs.items()):
        if len(where) != 1 or name.startswith(("__", "test", "main")) or name in attr_called or name in method_defs:
            continue
        n = sum(1 for p, b in bare.items() if name in b and p not in where)
        if 3 <= n <= 10:
            cands.append(name)
    if not cands:
        return None
    name = rng.choice(cands)
    return dict(name=name, ask=(f"List the paths (exactly as written in the '===== FILE:' headers) of every file in the dump "
                                f"that calls the module-level function `{name}` (as `{name}(...)` or `module.{name}(...)`), excluding the file that defines it. "
                                f"Answer with a JSON list of strings."))


def build_prompt(url, target_tokens, seed, suite="both", counter=None):
    """counter: optional fn(messages)->tokens for engines without /apply-template + /tokenize (e.g. Strata)."""
    rng = random.Random(seed)
    facts = make_facts(rng) if suite in ("easy", "both") else {}
    if suite in ("hard", "both"):
        facts.update(make_hard_facts(random.Random(seed * 7919 + 1)))
    ack = rand_id(rng, 8)

    def render(body):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": body + q_text}]
        r = requests.post(f"{url}/apply-template", json={"messages": msgs}, timeout=600)
        r.raise_for_status()
        return msgs, r.json()["prompt"]

    def ntok(text):
        r = requests.post(f"{url}/tokenize", json={"content": text, "add_special": False}, timeout=600)
        r.raise_for_status()
        return len(r.json()["tokens"])

    # Gather code chunks with a char budget, then trim to exact token count.
    files = code_files(seed)
    chars_per_tok = 3.3
    budget = int(target_tokens * chars_per_tok * 1.6)
    chunks, total = [], 0
    for fp in files:
        try:
            s = open(fp, errors="replace").read()
        except OSError:
            continue
        if len(s) > 60000:
            s = s[:60000]
        chunks.append(f"\n// ===== FILE: {os.path.relpath(fp, os.path.expanduser('~'))} =====\n{s}")
        total += len(chunks[-1])
        if total > budget:
            break
    hay = "".join(chunks)

    agg = None
    if suite in ("hard", "both"):
        # Planted cross-file aggregation: one definition, k call sites in different real files, plus decoys.
        arng = random.Random(seed * 104729 + 3)
        fn = f"lrr_{rand_id(arng, 5).lower()}_dispatch"
        k = arng.randint(4, 7)
        facts["_agg_def"] = dict(depth=arng.uniform(0.02, 0.15), text=f"def {fn}(payload, *, retries=3):\n    return _route(payload, retries)\n")
        for i in range(k):
            facts[f"_agg_call{i}"] = dict(depth=0.18 + 0.78 * (i + arng.random()) / k, text=f"    _res = {fn}(job.payload, retries=2)\n")
        facts["_agg_decoy1"] = dict(depth=arng.uniform(0.3, 0.9), text=f"    _res = {fn}_v2(job.payload)\n")
        facts["_agg_decoy2"] = dict(depth=arng.uniform(0.3, 0.9), text=f"    # TODO: do not call {fn}( here until the queue is drained\n")
        agg = dict(name=fn)
        facts["callers"] = dict(depth=None, expect=None, ask=(
            f"List the paths (exactly as written in the '===== FILE:' headers) of every file in the dump that calls "
            f"`{fn}(...)`, excluding the file that defines it. Answer with a JSON list of strings."))
    planted = sorted([(v["depth"], v["text"]) for v in facts.values() if v.get("depth") is not None])
    questions = {k: v["ask"] for k, v in facts.items() if not k.startswith("_")}
    q_text = ("\n\n=== END OF DUMP ===\nAnswer these questions using only the dump above. "
              "Return one JSON object with exactly these keys (plus \"ack\"):\n" +
              "\n".join(f"- \"{k}\": {q}" for k, q in questions.items()))
    system = SYSTEM.format(ack=ack)

    def assemble(n_chars):
        h = hay[:n_chars]
        out, last = [], 0
        for depth, text in planted:
            pos = int(depth * len(h))
            nl = h.rfind("\n", 0, pos)
            pos = nl + 1 if nl > 0 else pos
            out.append(h[last:pos]); out.append(text); last = pos
        out.append(h[last:])
        return "".join(out)

    # Search haystack chars for the SMALLEST prompt with n >= target (brief §4.4: "at least"),
    # accepting anything in [target, target + slack]. Full templated prompt is counted.
    slack = 256
    lo, hi = 1000, len(hay)
    best = None
    for _ in range(40):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        if counter is not None:
            body = assemble(mid)
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": body + q_text}]
            prompt, n = None, counter(msgs)
        else:
            msgs, prompt = render(assemble(mid))
            n = ntok(prompt)
        if n >= target_tokens:
            if best is None or n < best[1]:
                best = (mid, n, msgs, prompt)
            if n <= target_tokens + slack:
                break
            hi = mid - 1
        else:
            lo = mid + 1
    if best is None:
        raise SystemExit(f"haystack too small to reach {target_tokens} tokens")
    mid, n, msgs, prompt = best
    if agg:
        facts["callers"]["expect"] = callers_in(assemble(mid), agg["name"])
    expected = {k: v["expect"] for k, v in facts.items() if not k.startswith("_")}
    expected["ack"] = ack
    return dict(messages=msgs, prompt=prompt, prompt_tokens=n, expected=expected, seed=seed)


# ---------------------------------------------------------------- scoring

HARD_KEYS = {"var_chain", "billing_fee", "migration_date", "capacity", "callers"}
CALLERS_F1_OK = 0.8


def extract_json(text):
    # Final answer only: drop reasoning. The opening <think> may be in the prompt, so cut at the last </think>.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    dec = json.JSONDecoder()
    found = None
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                found = obj  # keep the last complete object
    return found


def norm(v):
    if isinstance(v, list):
        return sorted(int(x) if str(x).strip().lstrip("-").isdigit() else str(x).strip() for x in v)
    s = str(v).strip().strip(".").strip('"')
    return int(s) if s.lstrip("-").isdigit() else s


def score(answer_text, expected):
    obj = extract_json(answer_text) or {}
    res = {}
    for k, exp in expected.items():
        got = obj.get(k)
        if k == "callers":
            g = {str(x).strip().lstrip("./") for x in got} if isinstance(got, list) else set()
            e = set(exp)
            tp = sum(1 for x in g if any(x == y or y.endswith("/" + x) or x.endswith("/" + y) for y in e))
            prec = tp / len(g) if g else 0.0
            rec = tp / len(e) if e else 0.0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            res[k] = dict(expected=exp, got=got, ok=f1 >= CALLERS_F1_OK, f1=round(f1, 3))
            continue
        try:
            ok = got is not None and norm(got) == norm(exp)
        except Exception:
            ok = False
        if not ok and isinstance(exp, str) and got is not None and exp in str(got):
            ok = True  # tolerate extra words around an exact id
        res[k] = dict(expected=exp, got=got, ok=bool(ok))
    res["_json_ok"] = obj != {}
    keys = [k for k in res if not k.startswith("_")]
    res["_score"] = sum(res[k]["ok"] for k in keys) / len(keys)
    hard = [k for k in keys if k in HARD_KEYS]
    easy = [k for k in keys if k not in HARD_KEYS]
    res["_score_easy"] = sum(res[k]["ok"] for k in easy) / len(easy) if easy else None
    res["_score_hard"] = sum(res[k]["ok"] for k in hard) / len(hard) if hard else None
    return res


# ---------------------------------------------------------------- run

def main():  # noqa: C901
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--tokens", type=int, required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-new", type=int, default=16384)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--suite", default="both", choices=["easy", "hard", "both"])
    ap.add_argument("--save-prompt", default="", help="write messages+expected to this JSON (for cloud comparison)")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--prompt-file", default="", help="replay a saved prompt (identical text across models)")
    a = ap.parse_args()

    t0 = time.time()
    if a.prompt_file:
        pf = json.load(open(a.prompt_file))
        r = requests.post(f"{a.url}/apply-template", json={"messages": pf["messages"]}, timeout=600); r.raise_for_status()
        prompt = r.json()["prompt"]
        n = len(requests.post(f"{a.url}/tokenize", json={"content": prompt, "add_special": False}, timeout=600).json()["tokens"])
        p = dict(messages=pf["messages"], prompt=prompt, prompt_tokens=n, expected=pf["expected"], seed=pf["seed"])
        a.seed, a.suite = pf["seed"], pf["suite"]
    else:
        p = build_prompt(a.url, a.tokens, a.seed, a.suite)
    t_build = time.time() - t0
    print(f"[build] prompt_tokens={p['prompt_tokens']} target={a.tokens} ({t_build:.0f}s)", flush=True)
    if a.save_prompt:
        os.makedirs(os.path.dirname(a.save_prompt) or ".", exist_ok=True)
        json.dump(dict(messages=p["messages"], expected=p["expected"], prompt_tokens_builder=p["prompt_tokens"],
                       seed=a.seed, suite=a.suite, target_tokens=a.tokens), open(a.save_prompt, "w"))
    if a.build_only:
        return

    # Raw completion with the exact templated prompt so the counted tokens are what runs.
    t1 = time.time()
    r = requests.post(f"{a.url}/completion", json={
        "prompt": p["prompt"], "n_predict": a.max_new, "temperature": 0.6, "top_p": 0.95, "top_k": 20,
        "seed": a.seed, "cache_prompt": False, "return_tokens": False}, timeout=24 * 3600)
    r.raise_for_status()
    out = r.json()
    wall = time.time() - t1
    tim = out.get("timings", {})
    res = dict(label=a.label, suite=a.suite, seed=a.seed, prompt_file=a.prompt_file or None, target_tokens=a.tokens,
               prompt_tokens_counted=p["prompt_tokens"],
               prompt_tokens_server=tim.get("prompt_n"), tokens_evaluated=out.get("tokens_evaluated"),
               truncated=out.get("truncated"), stop_type=out.get("stop_type"),
               output_tokens=tim.get("predicted_n"),
               prefill_s=(tim.get("prompt_ms") or 0) / 1000, prefill_tps=tim.get("prompt_per_second"),
               gen_s=(tim.get("predicted_ms") or 0) / 1000, gen_tps=tim.get("predicted_per_second"),
               wall_s=wall, build_s=t_build, expected=p["expected"])
    res["scores"] = score(out.get("content", ""), p["expected"])
    res["answer_tail"] = out.get("content", "")[-4000:]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1, default=str)
    s = res["scores"]
    print(f"[done] score={s['_score']:.2f} easy={s['_score_easy']} hard={s['_score_hard']} json={s['_json_ok']} truncated={res['truncated']} "
          f"prompt_n={res['prompt_tokens_server']} prefill={res['prefill_s']:.0f}s ({res['prefill_tps']}) "
          f"gen={res['output_tokens']} tok @ {res['gen_tps']}", flush=True)
    for k, v in s.items():
        if not k.startswith("_"):
            print(f"   {'OK ' if v['ok'] else 'BAD'} {k}: expected={v['expected']} got={v['got']}")


if __name__ == "__main__":
    main()
