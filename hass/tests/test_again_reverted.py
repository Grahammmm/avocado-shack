"""AV2137-01 (H05/H06): `again <code>` also re-drafts a change that was undone in the last 7 days (counted from the undo's own
applied_at), as a new draft with a new code and expiry, only when the site as it is now would end every record it touches
with the values the original change wrote. It still needs `yes <new code>`; an undo's code, an old undo and photo drafts refuse.
Run: python3 -B -m unittest hass.tests.test_again_reverted -v
"""

import json
import unittest
from datetime import timedelta

from hass import editor
from hass.tests.test_again import drift
from hass.tests.test_editor import git
from hass.tests.test_undo import H06TestCase

PRODUCT = "photo-product-001"
WEEK = timedelta(days=7)
NOT_AVAILABLE = "{code}: the draft details are not available any more."


class UndoneAgainTests(H06TestCase):
    def undone(self, text="desc"):
        """Apply `text`, undo it (yes), and stamp the undo as applied `ago` before now; return (original row, undo row)."""
        self.apply(text)
        self.assertEqual(self.say("undo"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        original, undo = self.drafts()[-2:]
        self.assertEqual(original["state"], "reverted")
        return original, undo

    def row(self, code):
        return next(d for d in self.drafts() if d["code"] == code)

    def stamp(self, undo, applied_at):
        path = self.repo.state / "changes" / f"{undo['change_id']}.json"
        doc = json.loads(path.read_text("utf-8"))
        editor._write_json(path, {**doc, "applied_at": applied_at})

    def at(self, undo, delta):
        self.stamp(undo, (self.now - delta).isoformat())

    def again(self, code, expect="again"):
        self.assertEqual(self.say(f"again {code}"), expect)
        return self.replies()

    def edit_product(self, **fields):
        path = self.repo.wt / "hass/content/products.json"
        doc = json.loads(path.read_text("utf-8"))
        next(p for p in doc["products"] if p["id"] == PRODUCT).update(fields)
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")
        git(self.repo.wt, "commit", "-q", "-a", "-m", "site moved on")
        self.base = self.count()

    def refused(self, code, text):
        before, commits = self.drafts(), self.commits()
        self.assertEqual(self.again(code), [text])
        self.assertEqual((self.drafts(), self.commits()), (before, commits))  # no row, no approval, no change

    def test_undo_again_named_yes_restores_original(self):
        before = self.product(PRODUCT)["description"]
        original, undo = self.undone()
        self.assertEqual(self.product(PRODUCT)["description"], before)
        self.at(undo, timedelta(hours=1))
        commits = self.commits()
        [reply] = self.again(original["code"], "proposed")
        self.assertIn("Ripe and creamy.", reply)
        old, _undo, new = self.drafts()
        self.assertEqual((old["state"], new["state"], new["reason"]), ("reverted", "proposed", f"again:{original['code']}"))
        self.assertNotEqual(new["code"], original["code"])
        self.assertEqual((new["expires_at"], self.commits()), ((self.now + timedelta(seconds=600)).isoformat(), commits))  # nothing saved yet
        self.assertEqual(self.say(f"yes {original['code']}"), "no-target")  # the old code never approves it
        self.replies()
        self.assertEqual(self.say("yes"), "no-target")  # a bare yes never does either
        self.replies()
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        self.assertEqual((self.commits(), self.product(PRODUCT)["description"]), (commits + 1, "Ripe and creamy."))
        self.assertEqual(self.say("undo"), "proposed")  # the new change undoes like any other

    def test_later_edit_to_the_same_record_refuses(self):
        original, undo = self.undone()
        self.at(undo, timedelta(hours=1))
        self.edit_product(name="Renamed since")  # another field of a record the change touches
        self.refused(original["code"], drift(original["code"]))
        self.assertEqual(self.row(original["code"])["state"], "reverted")

    def test_an_undos_own_code_refuses(self):
        original, undo = self.undone()
        self.at(undo, timedelta(hours=1))
        self.refused(undo["code"], "That code is for an undo. Use again with the original change's code.")
        self.assertEqual(self.say(f"undo {undo['code']}"), "no-target")  # never an undo of an undo
        self.assertEqual(self.replies(), [f"That code is for an undo. To bring the change back, send {'again ' + original['code']}."])
        self.assertEqual(len(self.drafts()), 2)

    def test_seven_day_window_counts_from_the_undo(self):
        original, undo = self.undone()
        for name, stamp, reply in (("future", (self.now + timedelta(seconds=1)).isoformat(), NOT_AVAILABLE),
                                   ("one second over", (self.now - WEEK - timedelta(seconds=1)).isoformat(), "{code} was undone more than 7 days ago; send the change again."),
                                   ("missing", None, NOT_AVAILABLE), ("naive", "2026-11-02T09:00:00", NOT_AVAILABLE)):
            with self.subTest(name):
                self.stamp(undo, stamp)
                self.refused(original["code"], reply.format(code=original["code"]))
        self.at(undo, WEEK)  # exactly seven days still counts, however old the original change is
        self.again(original["code"], "proposed")

    def test_unlinked_or_photo_originals_refuse(self):
        original, undo = self.undone()
        self.at(undo, timedelta(hours=1))
        stored = self.repo.state / "drafts" / f"{original['change_id']}.json"
        doc = json.loads(stored.read_text("utf-8"))
        ops = [{**doc["ops"][0], "args": {**doc["ops"][0]["args"], "photo": "x.jpg"}}]
        editor._write_json(stored, {**doc, "ops": ops})
        self.conv.db.execute("UPDATE drafts SET ops_json = ? WHERE row_id = ?", (json.dumps(ops), original["row_id"]))
        self.refused(original["code"], f"{original['code']} is a photo draft; send the photo again.")
        editor._write_json(stored, doc)
        self.conv.db.execute("UPDATE drafts SET ops_json = ? WHERE row_id = ?", (original["ops_json"], original["row_id"]))
        path = self.repo.state / "changes" / f"{original['change_id']}.json"
        record = json.loads(path.read_text("utf-8"))
        editor._write_json(path, {k: v for k, v in record.items() if k != "revertedBy"})  # no link to the undo
        self.refused(original["code"], NOT_AVAILABLE.format(code=original["code"]))


if __name__ == "__main__":
    unittest.main()
