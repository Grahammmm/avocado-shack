"""HRM-04: take down an S12-shaped listing through the real chat and local writer.

The fixture supplies identification/card pixels and a delivery receipt. The real NPP
job and Conversation bind approval to the real editor draft; no release push or
live-site check is attempted. S13 wording comes from Conversation.npp_posted.
"""

import hashlib
import json
import unittest
from datetime import timedelta
from pathlib import Path

from hass import conversation
from hass.npp.job import Card
from hass.skills.testkit import RecordingPreviewer, _clocked_editor
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_editor import git
from hass.tests.test_npp_job import Scheduler, Stages, Transport
from hass.tests.test_photo_draft import JPG, PNG
from hass.tests.test_set_photo import PhotoRepo

MAKER = {"key": "Fixture Orchard", "name": "Fixture Orchard", "place": "Test Town",
         "story": "Makes quince jelly."}
NAME, PRICE, ALT = "Fixture quince jelly", "12.34", "A jar on a table"
CATALOG = "storefront-mockup/catalog-products.js"
PRODUCERS = "storefront-mockup/producers.json"


class _ListingStages(Stages):
    def __init__(self, engine, root, new_maker):
        super().__init__(engine, root)
        self.new_maker = new_maker

    def render(self, work, listing):
        ops = [{"op": "maker.add", "args": MAKER}] if self.new_maker else []
        ops.append({"op": "product.add", "args": {
            "name": NAME, "brand": MAKER["name"], "producerKey": MAKER["key"], "category": "pantry",
            "description": "Quince jelly.", "sellingPrice": listing["price"],
            "photo": work.request["attachments"][0], "imageAlt": ALT,
        }})
        out = self.editor.prepare(ops)
        if out["result"] != "ok":
            raise AssertionError(out)
        draft = out["draft"]
        (path, digest), = draft["assets"].items()
        return Card(draft, PNG, "raw", path,
                    digest.removeprefix("sha256:"), "picture: your own photo")


class _ChatTransport(Transport):
    def __init__(self):
        super().__init__()
        self.previews = []

    def send(self, chat, text, attachments):
        if attachments:
            self.previews.append((text, tuple(Path(path).read_bytes() for path in attachments)))
        else:
            super().send(chat, text, attachments)


class _HidePreviewer(RecordingPreviewer):
    def capture(self, files, target, out_png, assets=None):
        self.catalog = files[CATALOG]
        return super().capture(files, target, out_png, assets=assets)


class NppUndoJourneyTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.now, self.serial = T0, 0
        self._clock = lambda: self.now
        self.engine = _clocked_editor(self)(self.repo.state)
        self.scheduler, self.transport = Scheduler(), _ChatTransport()
        self.previewer = _HidePreviewer()

    def say(self, text, *, photos=0):
        self.serial += 1
        self.now += timedelta(seconds=1)
        msg = conversation.Inbound(f"fixture-{self.serial}", CHAT, OWNER, text,
                                   received_at=self.now.isoformat(), attachments=photos)
        result = self.conv.handle(msg, forwarded_at=self.now)
        self.conv.flush(self.transport)
        return result

    def fetch(self, provider_id, count):
        return [JPG][:count]

    def site(self):
        return self.repo.read(CATALOG), self.repo.read(PRODUCERS)

    def commits(self):
        return int(git(self.repo.wt, "rev-list", "--count", "HEAD"))

    def assert_commit_delta(self, delta):
        self.assertEqual(self.commits(), self.base_count + delta)
        self.assertEqual(self.repo.status(), "")

    def publish(self, *, new_maker=True):
        if not new_maker:
            seed = self.engine.prepare([{"op": "maker.add", "args": MAKER}])["draft"]
            self.assertEqual(self.engine.apply(seed["change_id"], seed["draft_hash"])["result"], "applied")
        cfg_path = self.repo.state / "config.json"
        cfg = json.loads(cfg_path.read_text("utf-8"))
        cfg["settings"].update(SETTINGS, npp=True, approvalNeedsCode=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        stages = _ListingStages(self.engine, self.repo.media, new_maker)
        self.conv = conversation.Conversation(
            self.repo.state, self.engine, conversation.FixtureInterpreter({}), self._clock,
            self.previewer, photos=self, npp_stages=stages, npp_executor=self.scheduler,
            npp_receipt_for=self.transport.receipt_for,
        )
        self.addCleanup(self.conv.db.close)
        self.base_head, self.base_count, self.base_site = self.repo.head(), self.commits(), self.site()
        self.base_products, self.base_makers = self.repo.products(), self.repo.makers()
        self.assertEqual(self.say(f"sell ${PRICE}", photos=1), "npp-working")
        for _ in range(8):
            self.conv.flush(self.transport)
            if self.scheduler.steps:
                self.scheduler.run()
        self.assertFalse(self.scheduler.steps)
        job = self.conv.db.execute("SELECT job_id FROM npp_jobs").fetchone()[0]
        assert self.conv.npp is not None
        version = self.conv.npp.version(job, 1)
        self.assertEqual(version["state"], "queued", self.transport.texts)
        self.change = version["change_id"]
        draft = self.engine.show(self.change)["draft"]
        self.assertEqual([op["op"] for op in draft["ops"]],
                         ["maker.add", "product.add"] if new_maker else ["product.add"])
        self.pid = next(r["key"] for r in draft["records"] if r["collection"] == "products")
        self.transport.receipts[version["outbox_id"]] = dict(
            state="confirmed", png_sha256=version["card_png_sha"],
            provider_guid="fixture-card", confirmed_at=self.now.isoformat(),
        )
        self.conv.flush(self.transport)
        self.assert_commit_delta(0)
        self.assertEqual((self.repo.head(), self.site()), (self.base_head, self.base_site))
        self.assertEqual(self.say(f"yes {job}-1"), "approved")
        self.assert_commit_delta(1)
        self.assertEqual(git(self.repo.wt, "rev-parse", "HEAD^"), self.base_head)
        self.publish_code = self.conv.db.execute("SELECT code FROM drafts WHERE change_id=?", (self.change,)).fetchone()[0]
        self.product = self.repo.product(self.pid)
        public = next(p for p in self.repo.catalog() if p["id"] == self.pid)
        self.assertEqual((public["sellingPrice"], public["imageAlt"], public["producerKey"]),
                         (PRICE, ALT, MAKER["key"]))
        self.assertEqual(self.product["status"], "active")
        path = "storefront-mockup/" + public["image"]
        self.assertIn(path, self.repo.committed())
        self.assertEqual("sha256:" + hashlib.sha256(self.repo.read(path)).hexdigest(), draft["assets"][public["image"]])
        self.assertIn(MAKER["key"], json.loads(self.repo.read(PRODUCERS)))
        self.assertEqual(self.conv.npp_posted(self.change),
                         f"Posted: https://theavocadoman.com/?item={self.pid}#market (say undo to take it down)")
        self.posted_head = self.repo.head()

    def draft_hide(self):
        posted = self.site(), self.repo.products(), self.repo.makers()
        self.assertEqual(self.say("undo"), "proposed")
        self.assert_commit_delta(1)
        self.assertEqual(self.repo.head(), self.posted_head)
        self.assertEqual((self.site(), self.repo.products(), self.repo.makers()), posted)
        row, = self.conv.db.execute("SELECT code, change_id FROM drafts WHERE state='proposed'")
        self.hide_code, self.hide_change = row
        self.assertNotEqual(self.hide_code, self.publish_code)
        draft = self.engine.show(self.hide_change)["draft"]
        self.assertEqual(draft["ops"], [{"op": "history.revert", "args": {"changeId": self.change}}])
        text, pictures = self.transport.previews[-1]
        self.assertIn(NAME, text)
        self.assertIn("hidden", text)
        self.assertEqual(len(pictures), 1)
        self.assertEqual(self.previewer.catalog, self.base_site[0])
        return text

    def confirm_hide(self):
        self.assertEqual(self.say(f"yes {self.hide_code}"), "approved")
        self.assert_commit_delta(2)
        self.assertEqual(git(self.repo.wt, "rev-parse", "HEAD^"), self.posted_head)
        self.assertEqual(self.site(), self.base_site)
        self.assertEqual(self.repo.products(), self.base_products + [dict(self.product, status="hidden")])
        self.assertEqual(self.engine.show(self.change)["change"]["revertedBy"], self.hide_change)

    def test_c1_undo_drafts_hide(self):
        # Do not auto-hide on "undo" or reuse the publication approval.
        self.publish()
        preview = self.draft_hide()
        self.assertIn(f"yes {self.hide_code}", preview)

    def test_c2_yes_hides(self):
        # A preview alone is not enough: one coded yes must remove the public card in one commit.
        self.publish()
        self.draft_hide()
        self.confirm_hide()

    def test_c3_maker_rule(self):
        # history.UNDO_ADDITION: retain a newly added maker's record with hidden=True, not a deletion or a public orphan.
        self.publish()
        self.draft_hide()
        makers = self.repo.makers()
        self.confirm_hide()
        makers[MAKER["key"]]["hidden"] = True
        self.assertEqual(self.repo.makers(), makers)
        self.assertNotIn(MAKER["key"], json.loads(self.repo.read(PRODUCERS)))

    def test_c4_repeat_safe(self):
        # A new inbound message repeating either command must not write a second undo.
        self.publish()
        self.draft_hide()
        self.confirm_hide()
        head = self.repo.head()
        undone = self.site(), self.repo.products(), self.repo.makers()
        for text, reply in (("undo", "nothing to undo"), (f"yes {self.hide_code}", "already saved")):
            with self.subTest(command=text.split()[0]):
                self.assertEqual(self.say(text), "no-target")
                self.assertIn(reply, self.transport.texts[-1])
                self.assert_commit_delta(2)
                self.assertEqual(self.repo.head(), head)
                self.assertEqual((self.site(), self.repo.products(), self.repo.makers()), undone)

    def test_c5_known_maker(self):
        # Product-only publication must undo without hiding or rewriting the pre-existing maker.
        self.publish(new_maker=False)
        preview = self.draft_hide()
        self.confirm_hide()
        self.assertEqual(self.repo.makers(), self.base_makers)
        self.assertIn(MAKER["key"], json.loads(self.repo.read(PRODUCERS)))
        self.assertIn(f"yes {self.hide_code}", preview)
