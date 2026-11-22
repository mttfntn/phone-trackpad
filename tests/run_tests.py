"""Runs every test: the Python suite (unittest) and the phone page suite (node --test).

    python tests/run_tests.py                 # test this checkout
    python tests/run_tests.py --app-root DIR  # test another copy of the app folder (e.g. an old version)
    python tests/run_tests.py --python-only   # skip the page tests (no Node.js needed)

Use the Python that has the app's requirements installed (desktop/.venv on a launcher-made
setup). Ends with "N checks, M failed" and exits non-zero on any failure.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_python(verbosity):
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py", top_level_dir=str(HERE))
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    failed = len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)
    return result.testsRun, failed, len(result.skipped)


def run_node():
    node = shutil.which("node")
    if not node:
        print("Node.js not found: page tests NOT run.")
        return 0, 1
    files = sorted(str(p) for p in (HERE / "web").glob("*.test.mjs"))
    proc = subprocess.run([node, "--test", *files], capture_output=True, text=True, encoding="utf-8")
    out = proc.stdout + proc.stderr
    for line in out.splitlines():
        if line.startswith("not ok") or line.lstrip().startswith(("error:", "location:")):
            print(line)
    total = int((re.search(r"^# tests (\d+)", out, re.M) or [0, 0])[1])
    failed = int((re.search(r"^# fail (\d+)", out, re.M) or [0, 0])[1])
    if proc.returncode and not failed:
        print(out)
        failed = 1
    print(f"page tests: {total} run, {failed} failed")
    return total, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-root", help="app folder to test instead of ./desktop")
    ap.add_argument("--python-only", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if args.app_root:
        os.environ["APP_ROOT"] = str(Path(args.app_root).resolve())
    sys.path.insert(0, str(HERE))

    print(f"Python {sys.version.split()[0]} on {sys.platform}; app: {os.environ.get('APP_ROOT') or 'desktop/'}")
    py_total, py_failed, py_skipped = run_python(2 if args.verbose else 1)
    js_total = js_failed = 0
    if not args.python_only:
        js_total, js_failed = run_node()
    total, failed = py_total + js_total, py_failed + js_failed
    print(f"\n{total} checks ({py_total} Python, {js_total} page; {py_skipped} skipped), {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
