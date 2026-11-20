"""Offline S2 contracts at the real Codex and local transport boundaries."""
import base64
import json
import unittest

from hass import label_reader
from hass.npp import assets
from hass.npp.identify import ASSET, Identifier

PINNED = assets()
EXAMPLES = [row["output"] for row in json.loads(PINNED[1][ASSET + "examples.json"])["examples"]]


def runner_output(output):
    return {"ok": True, "text": json.dumps(output), "model": "fixture-returned-model"}


class IdentifyTests(unittest.TestCase):
    def test_one_photo_only_call_for_ordered_views_with_pinned_instructions(self):
        # Case 17: a split call or swapped front/back can identify the wrong listing.
        calls = []

        def run(request):
            calls.append(request)
            return runner_output(EXAMPLES[1])

        reading = Identifier(PINNED, runner=run).read((b"front of jam", b"back of jam"))
        self.assertEqual(len(calls), 1)
        req = calls[0]
        self.assertEqual([base64.b64decode(s.split(",")[1]) for s in req["images"]], [b"front of jam", b"back of jam"])
        self.assertNotIn("price", req["text"].casefold())  # existing Codex finance filter must admit the photo-only user part
        self.assertIn("Never infer", req["instructions"])
        self.assertIn("Lavender honey soy candle", req["instructions"])
        self.assertEqual((req["model"], req["effort"], req["timeout"]), ("gpt-6.2-sol", "low", 12))
        self.assertEqual(reading.receipt["model"], "fixture-returned-model")
        assert reading.evidence is not None
        self.assertEqual(reading.evidence["item"], "Raspberry Jam")
        self.assertEqual(reading.evidence["visible_claims"], ["Organic"])

    def test_nonfood_identity_and_screen_flag_survive_without_money_or_prose(self):
        # F9 / cases 14–15, 28b: preserve the product noun and photo safety,
        # but a shelf sticker or claim is not ordinary label wording.
        output = dict(EXAMPLES[2], item="lavender\t honey soy  candle", brand_on_label="iWax  LAB",
                      size_text="$8.00", label_words=["honey", "Organic", "$8.00", "honey"], has_person_or_screen=True)
        evidence = Identifier(PINNED, runner=lambda _: runner_output(output)).read((b"candle",)).evidence
        assert evidence is not None
        self.assertEqual((evidence["item"], evidence["kind"], evidence["brand_on_label"]),
                         ("Lavender Honey Soy Candle", "non-food", "iWax LAB"))
        self.assertIs(evidence["has_person_or_screen"], True)
        self.assertIsNone(evidence["size_text"])
        self.assertEqual(evidence["label_words"], ["honey"])
        self.assertEqual(evidence["visible_claims"], ["Organic"])
        self.assertNotIn("description", evidence)

    def test_closed_schema_rejects_extra_fields_invalid_flags_and_scores(self):
        # Case 18: malformed evidence must not authorize identification/polish/raw.
        for changes in ({"sellingPrice": "1.00"}, {"has_person_or_screen": 0}, {"confidence": {"item": True}},
                        {"confidence": dict(EXAMPLES[0]["confidence"], item=True)}, {"kind": "other"},
                        {"category_guess": "hardware"}, {"label_words": ["ok"] * 13}):
            with self.subTest(changes=changes):
                output = dict(EXAMPLES[0], **changes)
                result = Identifier(PINNED, runner=lambda _: runner_output(output)).read((b"fixture",))
                self.assertIsNone(result.evidence)
                self.assertEqual(result.receipt["error"], "identify-schema")
                self.assertFalse(result.receipt["schema_valid"])

    def test_invalid_primary_uses_one_local_attempt_only_inside_shared_budget(self):
        # A fallback that resets the deadline can block the worker beyond 28 s.
        for spent, want_timeouts in ((12, [16]), (28, [])):
            with self.subTest(spent=spent):
                now, timeouts = [0], []

                def run(_):
                    now[0] = spent
                    return runner_output({})

                def local(_, body, headers, timeout):
                    timeouts.append(timeout)
                    self.assertIn("images", json.loads(body)["messages"][1])
                    return 200, json.dumps({"done": True, "model": "qwen-fixture",
                                            "message": {"content": json.dumps(EXAMPLES[0])}}).encode()

                fixture = label_reader.LabelReader("http://127.0.0.1:11434", "qwen", transport=local)
                result = Identifier(PINNED, fixture, runner=run, clock=lambda: now[0]).read((b"fixture",))
                self.assertEqual(timeouts, want_timeouts)
                self.assertTrue(result.receipt["fallback"])
                if want_timeouts:
                    assert result.evidence is not None
                    self.assertEqual(result.evidence["item"], "Wood Glue")
                    self.assertEqual(result.receipt["model"], "qwen-fixture")
                else:
                    self.assertIsNone(result.evidence)
                    self.assertEqual(result.receipt["error"], "timeout")

    def test_no_readable_photo_does_not_call_either_reader(self):
        result = Identifier(PINNED, runner=lambda _: self.fail("called without photos")).read((b"",))
        self.assertIsNone(result.evidence)
        self.assertEqual(result.receipt["error"], "unreadable-photo")
