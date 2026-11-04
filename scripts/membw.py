"""Rough single-process RAM read bandwidth: multi-threaded numpy sum over a 8 GB array."""
import numpy as np, time, os
from concurrent.futures import ThreadPoolExecutor
n = 8 * 2**30 // 8
a = np.ones(n, dtype=np.float64)
for threads in (1, 8, 16, 32):
    chunks = np.array_split(a, threads * 4)
    with ThreadPoolExecutor(threads) as ex:
        best = 0
        for _ in range(3):
            t = time.perf_counter(); list(ex.map(np.sum, chunks)); dt = time.perf_counter() - t
            best = max(best, a.nbytes / dt / 1e9)
    print(f"threads={threads:2d} read_GBps={best:6.1f}")
