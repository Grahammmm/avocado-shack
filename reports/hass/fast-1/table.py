#!/usr/bin/env python3
"""Prints stage-bench-results.json as a markdown table (seconds after the owner pressed send). Usage: table.py RESULTS.json"""
import json, sys

COLS = ("webhook-in", "accepted", "ack-end", "post-end", "receiver-accepted", "worker-pickup", "interp-end", "handled",
        "reply-queued", "reply-pulled", "bb-send-end")
rows = json.load(open(sys.argv[1]))
print("| run | webhook | found by | " + " | ".join(COLS) + " |")
print("|---|---|---|" + "---|" * len(COLS))
for r in rows:
    s = r["stages_s_after_sent"]
    print(f"| {r['variant']} `{r['text']}` +{r['phase_s']:g}s | {'on' if r['webhook'] else 'off'} | {r['via']} | " + " | ".join(str(s.get(c, "-")) for c in COLS) + " |")

print()
print("| group | runs | end-to-end s (min / median / max) |")
print("|---|---|---|")
groups = {}
for r in rows: groups.setdefault((r["variant"], "webhook on" if r["webhook"] else "webhook off"), []).append(r["end_to_end_s"])
for (variant, hook), vals in groups.items():
    vals = sorted(vals)
    print(f"| {variant}, {hook} | {len(vals)} | {vals[0]} / {vals[len(vals) // 2]} / {vals[-1]} |")
