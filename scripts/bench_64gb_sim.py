"""Run the bench matrix (benchmarks/validation, the 2026-11-09 validation harness) against the 64 GB
simulation server on :8092.

usage: bench_64gb_sim.py OUTDIR [bench_matrix.py args...]
The harness is used unchanged; only the port differs, so the numbers compare directly with the full-RAM baseline.
"""
import runpy, sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "benchmarks/validation"
sys.path.insert(0, str(SCRIPTS))
import harness as H

H.PORT = 8092
sys.argv = [str(SCRIPTS / "bench_matrix.py")] + sys.argv[1:]
runpy.run_path(str(SCRIPTS / "bench_matrix.py"), run_name="__main__")
