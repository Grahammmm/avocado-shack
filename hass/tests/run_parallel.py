#!/usr/bin/env python3
"""Run the hass/tests unittest suite in parallel shards, preserving unittest's output format exactly.

Why: the suite is 2000+ tests in 238 modules and ran serially, which made it ~98% of the avocado
`check` job wall-clock. Each shard is a real `python3 -m unittest <modules> -v` run, so every result
header keeps the "=====" rule directly above it that bin/mergegate.py relies on to read failing test
ids. Shard outputs are buffered to separate files and printed one after another, never interleaved,
so that adjacency survives.

Same modules, same tests, same assertions as `python3 -m unittest discover -s hass/tests -t . -v`.
Exit status is 0 only when every shard exited 0.

Usage: python3 hass/tests/run_parallel.py [--jobs N] [--list]
  --jobs N   number of parallel shards (default: min(6, cpu_count), env HASS_TEST_JOBS overrides)
"""
import argparse, os, subprocess, sys, tempfile, time
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]


def modules():
    """Dotted module names unittest discover would collect, in the same (sorted) order."""
    return ["hass.tests." + p.stem for p in sorted(TESTS.glob("test_*.py"))]


def shard(mods, n):
    """Round-robin into n shards: neighbouring modules tend to be similar in cost, so round-robin
    balances better than contiguous blocks."""
    out = [[] for _ in range(n)]
    for i, m in enumerate(mods):
        out[i % n].append(m)
    return [s for s in out if s]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("HASS_TEST_JOBS") or 0))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    mods = modules()
    if a.list:
        print("\n".join(mods)); return 0
    if not mods:
        print("no hass/tests test_*.py modules found", file=sys.stderr)
        return 1
    jobs = a.jobs or min(6, os.cpu_count() or 1)
    jobs = max(1, min(jobs, len(mods)))
    groups = shard(mods, jobs)
    print(f"hass tests: {len(mods)} modules in {len(groups)} parallel shards", flush=True)
    t0 = time.time()
    procs, tmp = [], tempfile.mkdtemp(prefix="hass-shards-")
    for i, g in enumerate(groups):
        log = os.path.join(tmp, f"shard{i}.log")
        f = open(log, "wb")
        # -u: unbuffered. unittest writes its report to stderr while a test's own print() goes to
        # stdout; with stdout block-buffered, a test's output can flush between the "=====" rule and
        # the FAIL:/ERROR: header below it, and bin/mergegate.py then silently drops that failing
        # test id (observed on main job 126269370693: 4 failures in the log, 3 ids read). Unbuffered
        # stdout keeps the two streams in real order within a shard.
        p = subprocess.Popen([sys.executable, "-u", "-m", "unittest", "-v", *g],
                             cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT)
        procs.append((i, g, p, f, log))
    rc = 0
    for i, g, p, f, log in procs:
        p.wait(); f.close()
        if p.returncode != 0:
            rc = 1
    # print shard outputs one whole shard at a time: never interleaved, so the "=====" rule stays
    # directly above each FAIL:/ERROR: header (bin/mergegate.py parses test ids from that adjacency)
    for i, g, p, f, log in procs:
        print(f"\n===== shard {i}: {len(g)} modules, exit {p.returncode} =====", flush=True)
        sys.stdout.flush()
        with open(log, "rb") as fh:
            sys.stdout.buffer.write(fh.read())
        sys.stdout.buffer.flush()
    print(f"\nhass tests: {len(groups)} shards finished in {time.time()-t0:.0f}s, exit {rc}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
