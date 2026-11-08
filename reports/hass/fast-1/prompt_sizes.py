#!/usr/bin/env python3
"""HASS-FAST-1: size of the interpreter prompt by section, from the repo's public catalog (no owner data). Run from the repo root."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from hass import interpreter_prompt as ip  # noqa: E402
from hass.content_model import load_content  # noqa: E402
from hass.ops import load_registry  # noqa: E402

root = Path(__file__).resolve().parents[3]
prompt = ip.build(load_registry(), load_content(root / "hass" / "content"))
sections = prompt.split("\n\n")
heads = {"Rules:": "rules", "Operations": "operations", "Catalog.": "catalog (products + makers)", "Community.": "community (hikes, routes)", "Store.": "store"}
out, total = {}, len(prompt)
out["role+contract"] = len(sections[0]) + len(sections[1]) + 4
body = "\n\n".join(sections[2:])
parts = {}
for sec in sections[2:]:
    for h, name in heads.items():
        if sec.startswith(h): parts[name] = len(sec) + 2
out.update(parts)
static = out["role+contract"] + parts["rules"] + parts["operations"]
desc = sum(len(line) for line in prompt.splitlines() if line.startswith('"photo-product-') or line.startswith('"product'))
print(json.dumps({"total_chars": total, "approx_tokens_at_3p5_chars": round(total / 3.5), "static_prefix_chars": static,
                  "static_share": round(static / total, 3), "sections": out, "product_rows_chars": desc}, indent=1))
