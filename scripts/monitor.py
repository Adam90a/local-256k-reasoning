#!/usr/bin/env python3
"""Sample PRO 4000 (by UUID) + system RAM/CPU/swap every second to CSV until killed.
Writes <csv>.peaks.json on exit (SIGTERM/SIGINT)."""
import csv, json, signal, subprocess, sys, time, psutil
UUID = "GPU-4e9ed5ea-d6d0-183f-9335-fd87f65d3f16"
out = sys.argv[1]; pid = int(sys.argv[2]) if len(sys.argv) > 2 else None
f = open(out, "w", newline=""); w = csv.writer(f)
cols = ["t", "vram_mib", "gpu_util", "power_w", "temp_c", "sm_mhz", "ram_used_gb", "swap_used_gb", "cpu_pct", "proc_rss_gb", "swap_in_mbps", "swap_out_mbps"]
w.writerow(cols); peaks = {c: 0.0 for c in cols[1:]}
stop = False
def h(*_):
    global stop; stop = True
signal.signal(signal.SIGTERM, h); signal.signal(signal.SIGINT, h)
proc = psutil.Process(pid) if pid else None
start_sin = psutil.swap_memory().sin
t0 = time.time(); last = psutil.swap_memory(); lt = t0
while not stop:
    q = subprocess.run(["nvidia-smi", "-i", UUID, "--query-gpu=memory.used,utilization.gpu,power.draw,temperature.gpu,clocks.sm",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip().split(", ")
    vm = psutil.virtual_memory(); sw = psutil.swap_memory()
    try: rss = proc.memory_info().rss / 1e9 if proc else 0
    except psutil.Error: rss = 0
    now = time.time(); dt = max(now - lt, 1e-3)
    sin = (sw.sin - last.sin) / dt / 1e6; sout = (sw.sout - last.sout) / dt / 1e6; last, lt = sw, now
    row = [round(now - t0, 1), *[float(x) for x in q], round((vm.total - vm.available) / 1e9, 2),
           round(sw.used / 1e9, 2), psutil.cpu_percent(), round(rss, 2), round(sin, 1), round(sout, 1)]
    w.writerow(row); f.flush()
    for c, v in zip(cols[1:], row[1:]): peaks[c] = max(peaks[c], v)
    time.sleep(1)
peaks["swap_in_total_mb"] = round((psutil.swap_memory().sin - start_sin) / 1e6, 1)
json.dump(peaks, open(out + ".peaks.json", "w"), indent=1)
