"""Minimal test runner (no pytest on this machine). Exit code 0 only if every test passes."""
import sys, traceback
sys.path.insert(0, ".")
import tests.test_ledger as t
fails = 0
for name in sorted(n for n in dir(t) if n.startswith("test_")):
    try:
        getattr(t, name)(); print(f"PASS {name}")
    except Exception:
        fails += 1; print(f"FAIL {name}"); traceback.print_exc(limit=1)
print(f"{fails} failed")
sys.exit(1 if fails else 0)
