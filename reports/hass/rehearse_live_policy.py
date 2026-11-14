"""Scratch-only rehearsal (P-0b): run the real op registry at this checkout through the real LIVE policy.

HASS-LIVE-ADD-1 (G, 2026-11-09): "add a new product" is now ALLOWED (with its brand and maker, from the owner's own words); every row
that must stay private still prints REFUSED. Each row names what it expects; the script exits 1 if any row differs.

Uses a temporary writer repo + state with a private photo store (hass.tests.test_set_photo.PhotoRepo). No live state, no network,
no messages. Usage: python3 -B reports/hass/rehearse_live_policy.py <checkout>   (the checkout may be the one this file is in)
"""
import json
import sys
from pathlib import Path

CHECKOUT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(CHECKOUT))

from hass import editor, live_policy  # noqa: E402
from hass.ops import load_registry  # noqa: E402
from hass.tests.test_set_photo import FIXTURES, PhotoRepo  # noqa: E402

repo = PhotoRepo()
reg = load_registry()
sha = repo.store((FIXTURES / "pixel.jpg").read_bytes())
products = json.loads((CHECKOUT / "hass/content/products.json").read_text())
products = products if isinstance(products, list) else products.get("products", products)
pid, cat = products[0]["id"], products[0].get("category")
makers = json.loads((CHECKOUT / "hass/content/makers.json").read_text())["makers"]
mkey = next(iter(makers))
print("checkout", CHECKOUT.name, "ops loaded:", len(reg), "sample product id:", pid)

ALT = "A jar of quince jam on a plain counter"
NEW_MAKER = ("maker.add", {"key": "test-orchard", "name": "Test Orchard", "place": "Paso Robles, California",
                           "story": "Test Orchard is based in Paso Robles, California."})
NEW_PRODUCT = {"name": "Quince jam", "brand": "Test Orchard", "category": "pantry", "description": "Sweet and tart on warm toast.",
               "producerKey": "test-orchard", "photo": sha, "imageAlt": ALT}
SAID = "New quince jam from Test Orchard in Paso Robles, goes on the pantry shelf"
bad = []


def draft_for(label, expect, *ops, said=None):
    out = editor.prepare({"ops": [{"op": n, "args": a} for n, a in ops]}, state=str(repo.state), registry=reg)
    if out["result"] != "ok":
        print(f"{label:62s} PREPARE-{out['result']}: {str(out.get('problems') or out)[:110]}  MISMATCH (expected {expect})")
        bad.append(label)
        return None
    reasons = live_policy.check(out["draft"])
    if not reasons and said is not None and (unsaid := live_policy.unsaid(out["draft"], said)):
        reasons = [f"ASKED FIRST: not in the owner's words: {unsaid}"]
    got = "ALLOWED" if not reasons else "REFUSED"
    note = "" if got == expect else f"  MISMATCH (expected {expect})"
    bad.extend([label] if note else [])
    print(f"{label:62s} LIVE-POLICY: {got if not reasons else 'REFUSED ' + str(reasons)}{note}")
    return out["draft"]


draft_for("S1  product.add: new product, brand, new maker, photo", "ALLOWED", NEW_MAKER, ("product.add", NEW_PRODUCT), said=SAID)
draft_for("S1a product.add: same, on an existing maker", "ALLOWED", ("product.add", {**NEW_PRODUCT, "producerKey": mkey, "brand": makers[mkey]["name"]}),
          said=makers[mkey]["name"])
draft_for("S1b maker.add alone (no new product names it)", "REFUSED", NEW_MAKER)
draft_for("S1b2 maker.add with a web link", "REFUSED", ("maker.add", {**NEW_MAKER[1], "url": "https://www.example.com/orchard"}),
          ("product.add", NEW_PRODUCT))
draft_for("S1b3 maker.edit: place of an existing maker", "REFUSED", ("maker.edit", {"key": mkey, "place": "Somewhere, California"}))
draft_for("S1b4 maker.edit: link of an existing maker", "REFUSED", ("maker.edit", {"key": mkey, "url": "https://www.example.com/about"}))
draft_for("S1b5 maker.hide", "REFUSED", ("maker.hide", {"key": mkey, "withProducts": True}))
draft_for("S1e product.edit: brand of an existing product", "REFUSED", ("product.edit", {"id": pid, "brand": "Someone Else"}))
draft_for("S1e2 product.edit: producer of an existing product", "REFUSED", ("product.edit", {"id": pid, "producerKey": mkey}))
draft_for("S1f product.add: description says organic / grown in", "REFUSED", NEW_MAKER,
          ("product.add", {**NEW_PRODUCT, "description": "Organic quince jam grown in Paso Robles."}))
draft_for("S1g product.add: description has price words", "REFUSED", NEW_MAKER,
          ("product.add", {**NEW_PRODUCT, "description": "A fair price for a jar."}))
draft_for("S1h product.add: brand not in the owner's words", "REFUSED", NEW_MAKER, ("product.add", NEW_PRODUCT),
          said="New quince jam on the pantry shelf")
draft_for("S1i product.add: with an existing picture file (image)", "REFUSED", ("product.add", {
    k: v for k, v in NEW_PRODUCT.items() if k not in ("photo", "imageAlt", "producerKey")} | {"image": products[0]["image"], "brand": "Test Orchard"}))
draft_for("S3  store.confirm_selection (sold out, shelf check)", "ALLOWED", ("store.confirm_selection", {"no": [pid]}))
draft_for("S4  specials.add", "ALLOWED", ("specials.add", {"title": "Fresh bread Friday", "deal": "A free sample with any cheese", "end": "2026-11-14"}))
draft_for("S5  hike.create (meeting point trailhead gate)", "ALLOWED", ("hike.create", {
    "title": "Cass Hill walk", "date": "2026-11-14", "time": "09:00", "meetingPoint": "The trailhead gate", "rsvpEnabled": False}))
draft_for("S6  store.set_notice", "REFUSED", ("store.set_notice", {"text": "Come say hi, we are testing a new way to update the shop", "until": "2026-11-10"}))
draft_for("S8  store.set_phone (must be refused)", "REFUSED", ("store.set_phone", {"phone": "805 555 0100"}))
draft_for("S1c product.set_photo on an EXISTING product (real op)", "ALLOWED", ("product.set_photo", {"id": pid, "photo": sha, "imageAlt": ALT}))

rec = {"collection": "products", "before": {"id": pid, "name": "x", "brand": "b", "image": "old.jpg"},
       "after": {"id": pid, "name": "x", "brand": "b", "image": "assets/products/photo-0123456789ab.jpg", "imageAlt": "A bowl of quinces"}}
rec2 = {"collection": "products", "before": rec["before"], "after": {**rec["after"], "imageAlt": "Organic quinces from a farm"}}
for label, record, expect_refused in (("S1c2 product.set_photo, record shape (picture words only)", rec, False), ("S1d same, but the picture words claim organic/farm", rec2, True)):
    r = live_policy.check({"ops": [{"op": "product.set_photo", "args": {}}], "records": [record]})
    print(f"{label:62s} LIVE-POLICY: {'REFUSED ' + str(r) if r else 'ALLOWED'}")
    if bool(r) != expect_refused:
        bad.append(label)
undo = live_policy.check({"ops": [{"op": "history.revert", "args": {}}], "records": [{"collection": "products", "key": "x", "before": {
    "brand": "Test Orchard"}, "after": None}]})
print(f"{'S9  undo of the new product (always passes)':62s} LIVE-POLICY: {'ALLOWED' if not undo else 'REFUSED ' + str(undo)}")
if undo:
    bad.append("S9")
repo.cleanup()
print("ROWS OUT OF LINE:", bad or "none")
sys.exit(1 if bad else 0)
