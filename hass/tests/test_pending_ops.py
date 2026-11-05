"""AV0022-03 (H05): each waiting draft in `pending` carries its stored ops, so a correction resends the whole op;
an ops_json over OPS_PENDING_MAX bytes or not a JSON list is "opsOmitted": true (never truncated, never raised).
Run: python3 -B -m unittest hass.tests.test_pending_ops -v
"""

import copy
import json
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, interpreter_prompt
from hass.conversation import OPS_PENDING_MAX, PHOTO_QUESTION, Inbound, _pending_ops
from hass.tests import test_photo_draft as pd
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0, _ops
from hass.tests.test_editor import DESC
from hass.tests.test_hike_ops import HIKE
from hass.tests.test_interpreter_prompt import FIXTURE
from hass.tests.test_set_photo import PhotoRepo, _settings
from hass.tests.test_undo import H06TestCase

RULE = ('A correction to a pending draft resends every op of that draft in full with "revises" set to its code; '
        'copy each unchanged arg from its "ops" exactly.')


class Recorder(conversation.FixtureInterpreter):  # "make it 09:30" copies the first draft's ops, only time changed
    def __init__(self, mapping):
        super().__init__(mapping)
        self.pendings = []

    def interpret(self, text, pending, **kw):
        self.pendings.append(copy.deepcopy(pending))
        if text != "make it 09:30": return super().interpret(text, pending)
        ops = copy.deepcopy(pending[0]["ops"])
        ops[0]["args"]["time"] = "09:30"
        return {"ops": ops, "revises": pending[0]["code"]}


class HikePendingOpsTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping.update(hike=_ops(("hike.create", HIKE)),
                                   long=_ops((DESC, {"id": "photo-product-001", "description": "🥑" * 400})))
        self.interp = self.conv.interpreter = Recorder(self.interp.mapping)

    def pending(self):
        self.assertEqual(self.say("hello"), "unsupported")  # the request still runs
        self.replies()
        return self.interp.pendings[-1]

    def test_proposed_hike_entry_carries_every_arg_and_keeps_its_keys(self):
        draft, _reply = self.propose("hike")
        [entry] = self.pending()
        self.assertEqual(list(entry.items()), [("code", draft["code"]), ("state", "proposed"),  # keys and order kept
                                               ("summary", draft["summary"]), ("ops", [{"op": "hike.create", "args": HIKE}])])
        self.now = T0 + timedelta(seconds=601)  # expired drafts are still absent
        self.assertEqual(self.pending(), [])

    def test_correction_resends_the_whole_op_with_only_time_changed(self):
        old, _reply = self.propose("hike")
        self.assertEqual(self.say("make it 09:30"), "proposed")
        self.replies()
        self.assertEqual(self.interp.pendings[-1][0]["ops"], [{"op": "hike.create", "args": HIKE}])
        before, new = self.drafts()
        self.assertEqual((before["code"], before["state"], before["replaced_by"]), (old["code"], "rejected", new["code"]))
        self.assertEqual(json.loads(new["ops_json"]), [{"op": "hike.create", "args": {**HIKE, "time": "09:30"}}])
        [entry] = self.pending()  # only the new draft waits, carrying its new ops
        self.assertEqual((entry["code"], entry["ops"][0]["args"]), (new["code"], {**HIKE, "time": "09:30"}))

    def test_oversize_ops_are_omitted_never_truncated(self):
        big, _reply = self.propose("long")
        self.assertGreater(len(big["ops_json"].encode()), OPS_PENDING_MAX)
        hike, _reply = self.propose("hike")
        first, second = self.pending()
        self.assertEqual(first, {"code": big["code"], "state": "proposed", "summary": big["summary"], "opsOmitted": True})
        self.assertEqual((second["code"], second["ops"]), (hike["code"], [{"op": "hike.create", "args": HIKE}]))

    def test_corrupt_or_non_list_ops_json_is_omitted_and_the_request_runs(self):
        draft, _reply = self.propose("hike")
        for bad in ("{", '{"op": "hike.create"}', "null", ""):
            with self.subTest(bad=bad):
                self.conv.db.execute("UPDATE drafts SET ops_json = ? WHERE row_id = ?", (bad, draft["row_id"]))
                [entry] = self.pending()
                self.assertEqual((entry["code"], entry.get("opsOmitted")), (draft["code"], True))
                self.assertNotIn("ops", entry)


class PendingOpsUnitTests(unittest.TestCase):
    def test_boundary_and_too_deep(self):
        pad = OPS_PENDING_MAX - len('[{"args": {"t": ""}, "op": "x"}]')
        at = json.dumps([{"args": {"t": "a" * pad}, "op": "x"}], sort_keys=True)
        self.assertEqual(len(at.encode()), OPS_PENDING_MAX)
        self.assertEqual(_pending_ops(at), {"ops": json.loads(at)})
        self.assertEqual(_pending_ops(at.replace('"a', '"aa', 1)), {"opsOmitted": True})  # one byte over
        with mock.patch.object(conversation.json, "loads", side_effect=RecursionError):  # too deep: never raised
            self.assertEqual(_pending_ops("[[]]"), {"opsOmitted": True})

    def test_prompt_rule_once_and_within_cap(self):
        text = FIXTURE.read_text("utf-8")
        self.assertEqual((text.count(RULE), interpreter_prompt.RULES.count(RULE)), (1, 1))
        self.assertLess(len(text.encode("utf-8")), interpreter_prompt.PROMPT_MAX_BYTES)


class PhotoPendingOpsTests(unittest.TestCase):
    def test_needs_details_photo_entry_has_question_and_its_ops(self):
        repo, interp = PhotoRepo(), Recorder({})
        self.addCleanup(repo.cleanup)
        _settings(repo, **SETTINGS, mediaRoot=str(repo.media))
        conv = conversation.Conversation(str(repo.state), conversation.Editor(repo.state), interp, lambda: T0,
                                         photos=pd.FakePhotos())
        for pid, text, attachments, want in ((1, "", 1, "photo-draft"), (2, "hello", 0, "unsupported")):
            self.assertEqual(conv.handle(Inbound(f"m{pid}", CHAT, OWNER, text, received_at=T0.isoformat(),
                                                 attachments=attachments)), want)
        ops = [{"op": "product.set_photo", "args": {"photo": pd.SHA}}]
        self.assertEqual(interp.pendings[-1],
                         [{"code": pd.SHA[:4], "state": "needs-details", "question": PHOTO_QUESTION, "ops": ops,
                           "missing": ["id", "imageAlt"]}])


if __name__ == "__main__":
    unittest.main()
