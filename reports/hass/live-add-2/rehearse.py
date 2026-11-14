"""HASS-LIVE-ADD-2 rehearsal: one sample photo through the REAL house render on a scratch writer (no network, no live site).

Run from the repo root with the pinned-Pillow venv python:
    ~/.local/share/hass/venv/bin/python3 reports/hass/live-add-2/rehearse.py

It plays the case row live2-known-maker-house-picture through the real Conversation, Editor and ops (houseRender on), says
`yes <code>`, and copies the picture the editor committed to reports/hass/live-add-2/result-house-picture.jpg. The wall clock is
held at 2026-11-08 only so the shelf-check day in the row is stable. Nothing leaves the throwaway worktree.
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
FIXED = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


from hass import content_model, conversation, editor  # noqa: E402
for mod in (content_model, editor, conversation):
    if getattr(mod, "datetime", None) is datetime:
        mod.datetime = FixedDate
from hass.skills import testkit  # noqa: E402
import PIL  # noqa: E402

ROW_ID = "live2-known-maker-house-picture"
rows = {r["id"]: r for r in testkit.load_rows(str(REPO / "hass/tests/fixtures/skills/item_add/item.add.jsonl"))}
row = rows[ROW_ID]
skills = {s.name: s for s in testkit.registry_skills()}
mapping = dict(zip(row["texts"], row["replies"]))
sc = testkit.Scratch(mapping, skills, None, row.get("seed"), row.get("setup"), row["photos"], True, row.get("live") is True,
                     row.get("maker_pages"))
try:
    base = sc.head()
    for text in row["texts"]:
        disposition, said = sc.say(text)
        print("MIKE:", text)
        print("HASS:", "\n".join(said))
    code = sc.drafts()[-1]["code"]
    disposition, said = sc.say(f"yes {code}")
    print("MIKE: yes <code>")
    print("HASS:", "\n".join(said))
    files = [f for f in testkit._git(sc.wt, "diff", "--name-only", base, "HEAD").split("\n") if f]
    pictures = [f for f in files if f.startswith("storefront-mockup/assets/products/photo-")]
    print("PILLOW:", PIL.__version__)
    print("FILES:", json.dumps(files))
    assert len(pictures) == 1, pictures
    shutil.copyfile(sc.wt / pictures[0], OUT / "result-house-picture.jpg")
    print("PICTURE:", pictures[0])
finally:
    sc.close()
sample = REPO / row["photos"][0]
shutil.copyfile(sample, OUT / "sample-jar-white-sheet.jpg")
from PIL import Image  # noqa: E402
for name in ("sample-jar-white-sheet.jpg", "result-house-picture.jpg"):
    with Image.open(OUT / name) as im:
        print(name, im.format, im.size, im.mode, (OUT / name).stat().st_size, "bytes")
