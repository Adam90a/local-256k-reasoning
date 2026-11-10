"""Shared harness for the Strata validation run.

Python stdlib plus the engine checkout's own tokenizer and template code (run with ~/strata-nvfp4/.venv/bin/python).
- Token counts use the server's own tokenizer class and chat template (same code + files the server loads).
  The server's usage.prompt_tokens is recorded as the authoritative count.
- Requests go through the existing OpenAI endpoint, streamed, one at a time.
- A background sampler writes 1 s telemetry (both GPUs, host RAM, swap, PSI, engine RSS) to CSV.
- Safety gate: refuses to start while the server is busy; aborts on temperature / RAM / swap / PSI thresholds.
- No API keys are used or logged (the server runs without one).
"""
import csv, http.client, json, os, random, subprocess, threading, time, uuid
from pathlib import Path

HOST, PORT = "127.0.0.1", 8091
SNAP = Path.home() / ".cache/huggingface/hub/models--Maximilian228--Qwen3.8-Flash-Next-NVFP4-GPTQ-Strata/snapshots/9b70ad3f640b2546449bd05387407a64113acf8b"
TOKDIR = SNAP / "pack/tokenizer"

# abort thresholds
MAX_TEMP_C, TEMP_HOLD_S = 92, 30
MIN_MEMAVAIL_GIB = 10
MAX_SWAP_GROWTH_GIB = 2
MAX_PSI_FULL_AVG10 = 10.0


def engine_pid():
    out = subprocess.run(["pgrep", "-x", "strata"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


# ---------------------------------------------------------------- tokenizer / template
class Prompter:
    """The server's own tokenizer (tools/strata_tokenizer.py) and chat template class (serve/frontend.py)."""
    def __init__(self):
        import sys
        repo = Path.home() / "strata-nvfp4"
        sys.path[:0] = [str(repo), str(repo / "tools")]
        import strata_tokenizer as ST
        from serve.frontend import ChatTemplate
        vocab = json.loads((TOKDIR / "vocab.json").read_text(encoding="utf-8"))
        tokens = [None] * len(vocab)
        for t, i in vocab.items():
            tokens[i] = t
        merges = (TOKDIR / "merges.txt").read_text(encoding="utf-8").split("\n")
        types = json.loads((TOKDIR / "token_type.json").read_text())
        self.tok = ST.Tokenizer(tokens, merges, types)
        tpl = TOKDIR / "chat_template.jinja"
        self.tpl = ChatTemplate(tpl if tpl.exists() else repo / "serve/chat_template.jinja")

    def render(self, messages, thinking):
        return self.tpl.render(messages, tools=None, add_generation_prompt=True, enable_thinking=thinking)

    def count(self, messages, thinking):
        return len(self.tok.encode(self.render(messages, thinking), parse_special=True))

    def ntok(self, text):
        return len(self.tok.encode(text))

    def ids(self, text):
        return self.tok.encode(text)

    def decode(self, ids):
        return self.tok.decode(ids)


# ---------------------------------------------------------------- corpus of varied text
def load_corpus(seed=0):
    """Mixed documents: Python source, scripture prose, project docs. Shuffled per seed."""
    docs = []
    for p in sorted(Path("/usr/lib/python3.12").glob("*.py")):
        try:
            t = p.read_text(errors="ignore")
        except OSError:
            continue
        if 2000 < len(t) < 120000:
            docs.append(("code", p.name, t))
    for p in sorted((Path.home() / "bible-data/engwebu").rglob("*"))[:400]:
        if p.is_file() and p.stat().st_size > 2000:
            docs.append(("prose", p.name, p.read_text(errors="ignore")[:60000]))
    for p in sorted(Path.home().glob("strata-nvfp4/**/*.md"))[:200]:
        if "node_modules" not in str(p) and p.stat().st_size > 2000:
            docs.append(("docs", p.name, p.read_text(errors="ignore")[:60000]))
    random.Random(seed).shuffle(docs)
    return docs


def build_messages(prompter, target, corpus, seed, task, thinking=False):
    """User message = unique header + documents + task, sized so the rendered prompt is ~target tokens."""
    rng = random.Random(seed)
    header = f"[session {uuid.UUID(int=rng.getrandbits(128))}]\nBelow is a collection of documents.\n\n"
    tail = f"\n\n=== END OF DOCUMENTS ===\n\n{task}"
    base = prompter.count([{"role": "user", "content": header + tail}], thinking)
    budget = target - base
    start = rng.randrange(len(corpus))
    parts, used, i = [], 0, start
    while used < budget:
        kind, name, text = corpus[i % len(corpus)]
        block = f"\n--- document: {name} ({kind}) ---\n{text}\n"
        n = prompter.ntok(block)
        if used + n > budget:
            ids = prompter.ids(block)[: budget - used]
            block = prompter.decode(ids)
            n = prompter.ntok(block)
        parts.append(block)
        used += n
        i += 1
    body = "".join(parts)
    msgs = [{"role": "user", "content": header + body + tail}]
    # tighten: trim characters until we are not above target
    while prompter.count(msgs, thinking) > target:
        body = body[:-200]
        msgs = [{"role": "user", "content": header + body + tail}]
    return msgs, prompter.count(msgs, thinking)


# ---------------------------------------------------------------- server helpers
def get_json(path, timeout=10):
    c = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    c.request("GET", path)
    r = c.getresponse()
    body = r.read()
    c.close()
    return json.loads(body)


def requests_total():
    c = http.client.HTTPConnection(HOST, PORT, timeout=10)
    c.request("GET", "/metrics/prometheus")
    txt = c.getresponse().read().decode()
    c.close()
    for line in txt.splitlines():
        if line.startswith("strata:requests_total"):
            return int(float(line.split()[1]))
    return None


def preflight(wait_s=0):
    """True when the server is idle. Optionally waits up to wait_s for it to become idle."""
    t0 = time.time()
    while True:
        s = get_json("/status")
        if not s.get("busy") and not s.get("queued"):
            return True
        if time.time() - t0 > wait_s:
            return False
        time.sleep(5)


def last_request_record():
    m = get_json("/metrics")
    reqs = m.get("requests") or []
    return reqs[0] if reqs else None


def stream_chat(messages, max_tokens, thinking, seed, abort_evt=None, cancel_after_s=None,
                cancel_on_first_token=False, temperature=0.0, timeout=1800):
    """Streams one chat completion. Returns a dict with client-side timings and the text."""
    body = {"model": "qwen3.8-flash-next", "messages": messages, "max_tokens": max_tokens, "stream": True,
            "stream_options": {"include_usage": True}, "temperature": temperature, "seed": seed,
            "chat_template_kwargs": {"enable_thinking": thinking}}
    data = json.dumps(body).encode()
    c = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    t0 = time.time()
    out = {"t_send": t0, "ttft_s": None, "t_last": None, "content": "", "reasoning": "", "chunks": 0,
           "usage": None, "finish": None, "error": None, "cancelled": False, "http_status": None}
    try:
        c.request("POST", "/v1/chat/completions", body=data, headers={"Content-Type": "application/json"})
        r = c.getresponse()
        out["http_status"] = r.status
        if r.status != 200:
            out["error"] = r.read().decode(errors="replace")[:2000]
            return out
        buf = b""
        while True:
            if abort_evt is not None and abort_evt.is_set():
                out["cancelled"] = True
                out["error"] = "aborted by safety threshold"
                break
            if cancel_after_s is not None and time.time() - t0 > cancel_after_s:
                out["cancelled"] = True
                break
            line = r.readline()
            if not line:
                break
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                break
            try:
                ev = json.loads(payload)
            except ValueError:
                continue
            if ev.get("usage"):
                out["usage"] = ev["usage"]
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                txt = (d.get("content") or "")
                rtxt = (d.get("reasoning_content") or d.get("reasoning") or "")
                if (txt or rtxt) and out["ttft_s"] is None:
                    out["ttft_s"] = time.time() - t0
                    if cancel_on_first_token:
                        out["cancelled"] = True
                if txt or rtxt:
                    out["chunks"] += 1
                    out["t_last"] = time.time()
                out["content"] += txt
                out["reasoning"] += rtxt
                if ch.get("finish_reason"):
                    out["finish"] = ch["finish_reason"]
            if out["cancelled"]:
                break
    except Exception as e:  # noqa: BLE001 - record and continue
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            c.close()
        except Exception:
            pass
        out["t_end"] = time.time()
        out["total_s"] = out["t_end"] - t0
    return out


# ---------------------------------------------------------------- telemetry sampler
GPU_Q = "index,memory.used,utilization.gpu,temperature.gpu,power.draw,clocks.sm,clocks.mem,clocks_event_reasons.active"
FIELDS = ["t", "g0_mem_mib", "g0_util", "g0_temp", "g0_power_w", "g0_sm_mhz", "g0_mem_mhz", "g0_reasons",
          "g1_mem_mib", "g1_util", "g1_temp", "g1_power_w",
          "memavail_gib", "swap_used_gib", "psi_full_avg10", "psi_some_avg10", "engine_rss_gib"]


def _meminfo():
    d = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        d[k] = int(v.split()[0])
    return d


def _psi():
    some = full = None
    for line in open("/proc/pressure/memory"):
        kv = dict(x.split("=") for x in line.split()[1:])
        if line.startswith("some"):
            some = float(kv["avg10"])
        else:
            full = float(kv["avg10"])
    return some, full


class Sampler(threading.Thread):
    def __init__(self, csv_path, interval=1.0):
        super().__init__(daemon=True)
        self.path, self.interval = Path(csv_path), interval
        self.stop_evt, self.abort_evt = threading.Event(), threading.Event()
        self.abort_reason = None
        self.rows = []
        self.pid = engine_pid()
        mi = _meminfo()
        self.swap0 = (mi["SwapTotal"] - mi["SwapFree"]) / 2**20
        self._hot_since = None

    def sample(self):
        row = {"t": round(time.time(), 2)}
        out = subprocess.run(["nvidia-smi", f"--query-gpu={GPU_Q}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        for line in out:
            f = [x.strip() for x in line.split(",")]
            g = f"g{f[0]}"
            row[f"{g}_mem_mib"], row[f"{g}_util"], row[f"{g}_temp"], row[f"{g}_power_w"] = f[1], f[2], f[3], f[4]
            if g == "g0":
                row["g0_sm_mhz"], row["g0_mem_mhz"], row["g0_reasons"] = f[5], f[6], f[7]
        mi = _meminfo()
        row["memavail_gib"] = round(mi["MemAvailable"] / 2**20, 2)
        row["swap_used_gib"] = round((mi["SwapTotal"] - mi["SwapFree"]) / 2**20, 2)
        row["psi_some_avg10"], row["psi_full_avg10"] = _psi()
        try:
            for line in open(f"/proc/{self.pid}/status"):
                if line.startswith("VmRSS"):
                    row["engine_rss_gib"] = round(int(line.split()[1]) / 2**20, 2)
        except (OSError, TypeError):
            row["engine_rss_gib"] = None
        return row

    def check(self, row):
        t = float(row.get("g0_temp") or 0)
        if t >= MAX_TEMP_C:
            self._hot_since = self._hot_since or time.time()
            if time.time() - self._hot_since >= TEMP_HOLD_S:
                return f"GPU0 temperature {t} C for {TEMP_HOLD_S}s"
        else:
            self._hot_since = None
        if row["memavail_gib"] < MIN_MEMAVAIL_GIB:
            return f"MemAvailable {row['memavail_gib']} GiB < {MIN_MEMAVAIL_GIB}"
        if row["swap_used_gib"] - self.swap0 > MAX_SWAP_GROWTH_GIB:
            return f"swap grew {row['swap_used_gib'] - self.swap0:.2f} GiB"
        if row["psi_full_avg10"] > MAX_PSI_FULL_AVG10:
            return f"memory PSI full avg10 {row['psi_full_avg10']}"
        if self.pid and not Path(f"/proc/{self.pid}").exists():
            return "engine process disappeared"
        return None

    def run(self):
        new = not self.path.exists()
        with open(self.path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            while not self.stop_evt.is_set():
                t0 = time.time()
                try:
                    row = self.sample()
                    self.rows.append(row)
                    w.writerow(row)
                    fh.flush()
                    why = self.check(row)
                    if why and not self.abort_evt.is_set():
                        self.abort_reason = why
                        self.abort_evt.set()
                except Exception as e:  # noqa: BLE001
                    print("sampler error:", e, flush=True)
                self.stop_evt.wait(max(0.0, self.interval - (time.time() - t0)))

    def window(self, t0, t1):
        return [r for r in self.rows if t0 <= r["t"] <= t1]

    @staticmethod
    def peaks(rows):
        def mx(k):
            v = [float(r[k]) for r in rows if r.get(k) not in (None, "", "[N/A]")]
            return max(v) if v else None

        def mn(k):
            v = [float(r[k]) for r in rows if r.get(k) not in (None, "", "[N/A]")]
            return min(v) if v else None
        return {"g0_mem_mib_peak": mx("g0_mem_mib"), "g1_mem_mib_peak": mx("g1_mem_mib"),
                "g0_temp_peak": mx("g0_temp"), "g0_power_peak_w": mx("g0_power_w"), "g0_util_peak": mx("g0_util"),
                "g0_sm_mhz_min": mn("g0_sm_mhz"), "memavail_gib_min": mn("memavail_gib"),
                "swap_used_gib_max": mx("swap_used_gib"), "engine_rss_gib_peak": mx("engine_rss_gib"),
                "psi_full_avg10_max": mx("psi_full_avg10"),
                "throttle_reasons_seen": sorted({r.get("g0_reasons") for r in rows if r.get("g0_reasons")})}
