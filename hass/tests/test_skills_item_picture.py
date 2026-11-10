"""SKILLS-ITEMPIC-1: the item.picture skill (replace one product's picture; reports/hass/SKILLS-SPEC.md 3.5, card 15).

Proves, against the real content and the synthetic photos of #504: the registration and lint, the pure plan and its guards
(hidden or held, already this photo, one photo one product, a caption that says what the photo shows, D1), the strict voice
of every fixed sentence, the real dispatcher and editor path with the owner's yes and undo, and the house-picture advice with
the houseRender flag off (a warning he may approve knowingly, D6) and on (the installer's own retake refusal, item.add parity).
The case rows themselves run through the real Conversation and Editor: python3 -B hass/skills/testkit.py run
hass/tests/fixtures/skills/item_picture/item.picture.jsonl (and test_skills_cases).
Run: python3 -B -m unittest hass.tests.test_skills_item_picture -v
"""
import copy
import hashlib
import json
import sys
import types
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from hass import conversation, editor, live_policy, voice
from hass.content_model import REPO_ROOT, load_and_validate
from hass.ops import load_registry, photos
from hass.skills import dispatch, item_add, item_picture as ip, load_skills, skill_lint, testkit
from hass.skills.model import Registry, lint_plan_output

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
SYN = "reports/hass/newitem-1/synthetic/"
JAR, PNG, BUSY, SMALL = SYN + "jar-white-sheet.jpg", SYN + "bottle-bench-png.png", SYN + "bag-red-cloth.jpg", SYN + "bag-bench-small.jpg"
SHA = {f: hashlib.sha256((REPO_ROOT / f).read_bytes()).hexdigest() for f in (JAR, PNG, BUSY, SMALL)}
LEMONS, HELD, GUAC = "photo-product-017", "photo-product-040", "photo-product-031"


def ctx(*texts, content=CONTENT, **extra):
    return SimpleNamespace(today="2026-11-08", content=content, texts=list(texts), **extra)


def refusal(slots, *texts, **extra):
    with unittest.TestCase().assertRaises(ip.Refusal) as caught:
        ip.plan_picture(slots, ctx(*texts, **extra))
    caught.exception.reply = voice.plain(caught.exception.reply)  # the owner reads it without the quote marks
    return caught.exception


def with_product(pid, **fields):
    content = copy.deepcopy(CONTENT)
    next(p for p in content.products if p["id"] == pid).update(fields)
    return content


class Declaration(unittest.TestCase):
    def test_discovered_without_dispatch_edits_and_lints(self):
        registry = load_skills()
        self.assertIs(registry.get("item.picture"), ip.ITEM_PICTURE)
        ops = load_registry()
        self.assertEqual(skill_lint(registry, ops), [])  # the whole registry: no trigger in two skills
        self.assertEqual(skill_lint([ip.ITEM_PICTURE], ops, repo_root=REPO_ROOT), [])  # declaration and the case-file minima
        plan = ip.plan_picture({"item": LEMONS, "photo": SHA[JAR], "image_alt": "Lemons in a bowl"}, ctx())
        self.assertEqual(lint_plan_output(ip.ITEM_PICTURE, plan, ops), [])
        self.assertEqual(plan, [{"op": "product.set_photo", "args": {"id": LEMONS, "photo": SHA[JAR], "imageAlt": "Lemons in a bowl"}}])
        self.assertIs(ip.picture_review, item_add.picture_review)  # AV1109-10 handover: the exact advice item.picture shows
        self.assertEqual(ip.ITEM_PICTURE.live_class, "private-only")
        self.assertNotIn("item.picture", dispatch.RULES)  # no import-time rule registration: the guards are in the plan

    def test_every_owner_sentence_passes_the_voice_rules(self):
        fixed = [ip.ASK_ITEM, ip.ASK_PHOTO, ip.ONE_AT_A_TIME, ip.ONE_PLACE, ip.UNKNOWN, ip.NO_PHOTO, ip.NO_CATALOG, ip.ALT_ASK, ip.ALT_LONG,
                 ip.NOT_CHECKED, ip.OLD_STAYS, ip.ITEM_PICTURE.undo.residue]
        fixed += [reply.replace("<Product>", "Lemons") for _why, reply in ip.ITEM_PICTURE.refuse]
        fixed += [refusal({"item": HELD, "photo": SHA[JAR]}).reply]
        for text in fixed:
            with self.subTest(text=text):
                self.assertEqual(voice.check(voice.plain(text)), [])
                self.assertLessEqual(text.count("?"), 1, "one question at a time")


class Plan(unittest.TestCase):
    def test_active_named_caption_photo_first_and_missing_slots(self):
        out = ip.plan_picture({"item": LEMONS, "photo": SHA[JAR]}, ctx("new picture for the lemons"))
        self.assertEqual(out[0]["args"], {"id": LEMONS, "photo": SHA[JAR], "imageAlt": "Lemons"})  # the saved name
        out = ip.plan_picture({"item": "photo-product-172", "photo": SHA[JAR], "image_alt": "Etto rigatoni in the box"},
                              ctx("photo for the Etto rigatoni, in the box"))
        self.assertEqual(out[0]["args"]["imageAlt"], "Etto rigatoni in the box")  # his own words
        self.assertEqual(refusal({"photo": SHA[JAR]}, "this one is better").reply, ip.ASK_ITEM)
        self.assertEqual(refusal({"item": LEMONS}, "the lemons").reply, ip.ASK_PHOTO)
        self.assertEqual(refusal({"item": LEMONS, "photo": "IMG_1234"}, "the lemons").reply, ip.ASK_PHOTO)
        self.assertEqual([voice.plain(p) for p in ip.set_phrases({"item": LEMONS, "photo": SHA[JAR]}, ctx())],
                         ["the picture caption to \u201cLemons\u201d, and you can send a different one if you like"])
        self.assertEqual(ip.set_phrases({"item": LEMONS, "photo": SHA[JAR], "image_alt": "Lemons in a bowl"}, ctx()), [])

    def test_a_photo_id_he_never_sent_is_not_used(self):
        media = SimpleNamespace(photo_bytes=lambda sha: (REPO_ROOT / JAR).read_bytes() if sha == SHA[JAR] else None)
        self.assertEqual(refusal({"item": LEMONS, "photo": "a" * 64}, "the lemons", **vars(media)).reply, ip.NO_PHOTO)
        ip.plan_picture({"item": LEMONS, "photo": SHA[JAR]}, ctx("the lemons", **vars(media)))

    def test_hidden_held_unknown_and_direct_plan_refuse(self):
        self.assertIn("It is on hold until someone has looked at it.", refusal({"item": HELD, "photo": SHA[JAR]}).reply)
        hidden = with_product(GUAC, status="hidden")
        self.assertEqual(refusal({"item": GUAC, "photo": SHA[JAR]}, content=hidden).reply,
                         "Guacamole is hidden. Bring it back first, then I can change its picture.")
        self.assertEqual(refusal({"item": "photo-product-999", "photo": SHA[JAR]}).reply, ip.UNKNOWN)
        self.assertEqual(hidden.products, with_product(GUAC, status="hidden").products)  # nothing restored or unheld

    def test_missing_content_fails_closed_never_plans(self):
        full = {"item": LEMONS, "photo": SHA[JAR], "image_alt": "Lemons in a bowl"}
        for bad in (None, SimpleNamespace(), SimpleNamespace(content=None, texts=[])):
            with self.subTest(ctx=bad):
                with self.assertRaises(ip.Refusal) as caught:
                    ip.plan_picture(full, bad)
                self.assertEqual(caught.exception.reply, ip.NO_CATALOG)
                self.assertEqual(caught.exception.kind, "refuse")
                self.assertEqual(ip.set_phrases({"item": LEMONS, "photo": SHA[JAR]}, bad), [])
                self.assertEqual(ip.notes("item.picture", full, bad), {})

    def test_lists_without_determiners_ask_and_a_list_is_not_an_answer(self):
        slots = {"item": LEMONS, "photo": SHA[JAR]}
        for text in ("photos for lemons and plums", "photo of lemons & plums", "new photos for lemons, plums and limes",
                     "pictures for the lemons and plums", "photos for lemons plus the plums", "photos for lemons, and plums"):
            with self.subTest(text=text):
                self.assertEqual(refusal(slots, text).reply, ip.ONE_AT_A_TIME)
        for answer in ("lemons and plums please", "the lemons and the plums", "lemons & plums", "lemons, plums and limes"):
            with self.subTest(answer=answer):  # a list after the question is not the one product he was asked for
                self.assertEqual(refusal(slots, "photos for the lemons and the plums", answer).reply, ip.ONE_AT_A_TIME)
        ip.plan_picture(slots, ctx("photos for lemons and plums", "the lemons please"))  # one product settles it
        ip.plan_picture(slots, ctx("photos for lemons and plums", "lemons"))

    def test_one_product_whose_name_has_and_is_not_a_list(self):
        chips, cream = "photo-product-018", next(p["id"] for p in CONTENT.products if p["name"] == "Cookies and Cream chocolate")
        ip.plan_picture({"item": chips, "photo": SHA[JAR]}, ctx("photo for sea salt and tortilla chips"))
        ip.plan_picture({"item": cream, "photo": SHA[JAR]}, ctx("new photo for cookies and cream chocolate"))
        ip.plan_picture({"item": cream, "photo": SHA[JAR]}, ctx("photo for the cookies and cream chocolate please", "cookies and cream"))
        ip.plan_picture({"item": LEMONS, "photo": SHA[JAR]}, ctx("new photo for the lemons and thanks"))
        self.assertEqual(refusal({"item": cream, "photo": SHA[JAR]}, "photos for cookies and cream chocolate and lemons").reply,
                         ip.ONE_AT_A_TIME)  # the name is one product; the second "and" adds another
        self.assertEqual(refusal({"item": cream, "photo": SHA[JAR]}, "photos for cookies and lemons").reply, ip.ONE_AT_A_TIME)

    def test_comma_only_lists_ask_and_are_not_an_answer(self):
        slots = {"item": LEMONS, "photo": SHA[JAR]}
        for text in ("photos for lemons, plums", "new photo for the lemons, the plums", "photo of lemons, plums, limes",
                     "pictures for lemons,plums"):
            with self.subTest(text=text):  # a model-picked Lemon must not draft half of this
                self.assertEqual(refusal(slots, text).reply, ip.ONE_AT_A_TIME)
        for answer in ("lemons, plums please", "the lemons, the plums", "lemons, plums, limes"):
            with self.subTest(answer=answer):
                self.assertEqual(refusal(slots, "photos for lemons and plums", answer).reply, ip.ONE_AT_A_TIME)
                self.assertEqual(refusal(slots, "photos for lemons, plums", answer).reply, ip.ONE_AT_A_TIME)
        ip.plan_picture(slots, ctx("photos for lemons, plums", "the lemons please"))  # one product settles it
        ip.plan_picture(slots, ctx("photos for lemons and plums", "yes, the lemons"))

    def test_a_comma_before_a_caption_or_a_reply_word_is_one_product(self):
        etto = {"item": "photo-product-172", "photo": SHA[JAR], "image_alt": "Etto rigatoni in the box"}
        for text in ("photo for the Etto rigatoni, in the box", "photo for the Etto rigatoni, on the shelf",
                     "photo for the Etto rigatoni, please", "photo for the Etto rigatoni, 500 g", "photo for the Etto rigatoni, I took it today"):
            with self.subTest(text=text):
                ip.plan_picture(etto, ctx(text))
        slots = {"item": LEMONS, "photo": SHA[JAR]}
        for answer in ("the lemons, please", "no, the lemons", "ok, lemons", "lemons, definitely"):
            with self.subTest(answer=answer):
                ip.plan_picture(slots, ctx("photos for the lemons and the plums", answer))

    def test_multi_product_or_home_target_asks_then_single_answer_continues(self):
        slots = {"item": LEMONS, "photo": SHA[JAR]}
        self.assertEqual(refusal(slots, "photos for the lemons and the plums").reply, ip.ONE_AT_A_TIME)
        self.assertEqual(refusal(slots, "use this for the home page and the lemons").reply, ip.ONE_PLACE)
        self.assertEqual(refusal(slots, "use this photo for the lemons and the home page").reply, ip.ONE_PLACE)
        self.assertEqual(refusal(slots, "this is for both of them").reply, ip.ONE_AT_A_TIME)
        ip.plan_picture(slots, ctx("photos for the lemons and the plums", "the lemons"))  # his one answer settles it
        self.assertEqual(refusal(slots, "photos for the lemons and the plums", "ok").reply, ip.ONE_AT_A_TIME)  # not an answer
        self.assertEqual(refusal(slots, "the lemons", "photos for the lemons and the plums").reply, ip.ONE_AT_A_TIME)
        chips = "photo-product-018"  # one product whose name has 'and'-like words is still one product
        ip.plan_picture({"item": chips, "photo": SHA[JAR]}, ctx("photo for the salt and vinegar chips"))

    def test_same_photo_and_bad_alt_refuse(self):
        for ext in ("jpg", "png"):
            content = with_product(LEMONS, image=f"assets/products/photo-{SHA[JAR][:16]}.{ext}", imageAlt="Lemons")
            with self.subTest(ext=ext):
                self.assertEqual(refusal({"item": LEMONS, "photo": SHA[JAR], "image_alt": "Lemons on the counter"},
                                         content=content).reply, "Lemons already has this photo. Nothing changed.")
        other = with_product(LEMONS, image=f"assets/products/photo-{SHA[PNG][:16]}.png")  # another photo is not this one
        ip.plan_picture({"item": LEMONS, "photo": SHA[JAR]}, ctx(content=other))
        for alt in ("IMG_1234.jpg", "DSC01234", "photo", "the picture 2", "Screenshot 2026-11-08", SHA[JAR][:12] + " lemons",
                    "https://example.com/a", "x" * (photos.MAX_ALT + 1)):
            with self.subTest(alt=alt):
                with self.assertRaises(ip.Refusal) as caught:
                    ip.plan_picture({"item": LEMONS, "photo": SHA[JAR], "image_alt": alt}, ctx())
                self.assertEqual(caught.exception.kind, "question")

    def test_illustration_suffix_never_carried_d1(self):
        content = with_product(LEMONS, imageAlt="Lemons (illustration)")
        out = ip.plan_picture({"item": LEMONS, "photo": SHA[JAR]}, ctx(content=content))
        self.assertEqual(out[0]["args"]["imageAlt"], "Lemons")  # from the name, never the old caption
        out = ip.plan_picture({"item": LEMONS, "photo": SHA[JAR], "image_alt": "Lemons in a bowl (illustration)"}, ctx())
        self.assertEqual(out[0]["args"]["imageAlt"], "Lemons in a bowl")


class PictureAdvice(unittest.TestCase):
    def notes(self, path, house_render, **extra):
        data = (REPO_ROOT / path).read_bytes()
        c = ctx("the lemons", photo_bytes=lambda sha: data, house_render=house_render, **extra)
        return ip.notes("item.picture", {"item": LEMONS, "photo": hashlib.sha256(data).hexdigest()}, c)

    def test_house_flags_review_warnings(self):
        self.assertEqual(self.notes(BUSY, False)["warn"], [item_add.AS_TAKEN])  # flag off: a warning before his yes
        self.assertEqual(self.notes(BUSY, True)["warn"], [item_add.RETAKE_BUSY])
        self.assertEqual(self.notes(SMALL, True)["warn"], [item_add.RETAKE_SMALL])
        good = self.notes(JAR, True)
        self.assertEqual((good["say"][0], good["warn"]), (item_add.PICTURE_OK, []))
        self.assertIn(ip.OLD_STAYS, good["say"])

    def test_a_check_that_cannot_run_is_said_never_a_silent_pass(self):
        corrupt = ctx("the lemons", photo_bytes=lambda sha: b"not a photo", house_render=False)
        self.assertEqual(ip.notes("item.picture", {"item": LEMONS, "photo": SHA[JAR]}, corrupt)["warn"], [item_add.NO_BYTES])
        with mock.patch.object(ip.importlib.util, "find_spec", return_value=None):  # the picture tools are missing
            self.assertEqual(self.notes(JAR, True)["warn"], [ip.NOT_CHECKED])
        self.assertEqual(ip.notes("item.picture", {"item": LEMONS, "photo": SHA[JAR]}, ctx())["warn"], [ip.NOT_CHECKED])


# -- the real dispatcher, Conversation and Editor ------------------------------------------------------------------------
class _Interp(conversation.FixtureInterpreter):
    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        return super().interpret(text, pending)


class Chat:
    """One owner conversation on the throwaway repo with the real dispatcher, item.picture the only skill."""

    def __init__(self, photo_files, house_render=False):
        self.kit = testkit.Scratch({}, {"item.picture": ip.ITEM_PICTURE}, photos=list(photo_files))
        self.kit.conv.db.close()
        cfg = json.loads((self.kit.repo.state / "config.json").read_text("utf-8"))
        settings = {**cfg["settings"], "skills": {"mode": "both"}, **({"houseRender": True} if house_render else {})}
        editor._write_json(self.kit.repo.state / "config.json", {**cfg, "settings": settings})  # the editor's real flag
        self.files, self.now, self.n, self.out = {}, testkit.START, 0, self.kit.out
        self.interp = _Interp({})
        router = types.ModuleType("hass.skills.router")
        router.candidates = lambda text, hints=None, open_request=None, attachment=None, skills=(): [("item.picture", 10.0)]
        self._patch = mock.patch.dict(sys.modules, {"hass.skills.router": router})
        self._patch.start()
        source = SimpleNamespace(fetch=lambda pid, count: [(REPO_ROOT / self.files[pid]).read_bytes()] * count)
        self.conv = conversation.Conversation(str(self.kit.repo.state), self.kit.editor, self.interp, lambda: self.now,
                                              self.kit.previewer, photos=source,
                                              skills=Registry(skills={"item.picture": ip.ITEM_PICTURE}))
        self.base = testkit._git(self.kit.wt, "rev-parse", "HEAD").strip()

    def close(self):
        self._patch.stop()
        self.conv.db.close()
        self.kit.close()

    def say(self, text, reply=None, photo=None):
        if reply is not None:
            self.interp.mapping[text] = {"skill": "item.picture", "slots": reply, "revises": None}
        self.n += 1
        self.now += timedelta(minutes=1)
        pid = f"ip-{self.n}"
        if photo:
            self.files[pid] = photo
        msg = conversation.Inbound(pid, testkit.CHAT, testkit.OWNER, text, False, "new", self.now.isoformat(), 1 if photo else 0)
        disposition = self.conv.handle(msg)
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return disposition, "\n".join(row["text"] for row in self.out.sent[before:])

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def head(self):
        return testkit._git(self.kit.wt, "rev-parse", "HEAD").strip()

    def lemons(self):
        products = json.loads((self.kit.wt / "hass" / "content" / "products.json").read_text("utf-8"))["products"]
        return next(p for p in products if p["id"] == LEMONS)


class RealDispatcher(unittest.TestCase):
    def open(self, *files, house_render=False):
        chat = Chat(files, house_render)
        self.addCleanup(chat.close)
        return chat

    def test_photo_first_then_product_drafts_and_nothing_is_written_before_yes(self):
        chat = self.open(JAR)
        d1, r1 = chat.say("this one is better", {}, JAR)
        self.assertEqual((d1, r1), ("question", ip.ASK_ITEM))
        d2, r2 = chat.say("the lemons", {"item": "Lemons"})
        self.assertEqual(d2, "proposed")
        self.assertIn("I set: the picture caption to", r2)
        self.assertLess(r2.index(item_add.AS_TAKEN), r2.index("Reply yes to save it"))  # D6: the warning comes before his yes
        self.assertEqual(chat.head(), chat.base)
        self.assertEqual(chat.kit.previewer.requests[-1]["kind"], "product")

    def test_held_product_is_refused_by_name_and_no_draft(self):
        chat = self.open(JAR)
        d, r = chat.say("new photo for the raw milk cheese", {"item": "Raw milk white cheddar"}, JAR)
        self.assertEqual(d, "refused")
        self.assertIn("It is on hold until someone has looked at it.", r)
        self.assertEqual((chat.drafts(), chat.head()), ([], chat.base))

    def test_two_products_ask_and_his_answer_goes_on_to_one_draft(self):
        chat = self.open(JAR)
        d1, r1 = chat.say("photos for the lemons and the plums", {"item": "Lemons"}, JAR)
        self.assertEqual((d1, r1), ("question", ip.ONE_AT_A_TIME))
        d2, r2 = chat.say("the lemons please", {"item": "Lemons"})
        self.assertEqual(d2, "proposed")
        self.assertEqual(len(chat.drafts()), 1)
        self.assertEqual(json.loads(chat.drafts()[0]["ops_json"])[0]["args"]["id"], LEMONS)

    def test_flag_off_warning_is_approvable_knowingly_and_undo_keeps_both_files(self):
        chat = self.open(BUSY)
        old = chat.lemons()
        d, r = chat.say("new picture for the lemons", {"item": "Lemons"}, BUSY)
        self.assertEqual(d, "proposed")
        self.assertIn(item_add.AS_TAKEN, r)
        code = chat.drafts()[-1]["code"]
        chat.say(f"yes {code}")
        new = chat.lemons()
        target = f"assets/products/photo-{SHA[BUSY][:16]}.jpg"
        self.assertEqual((new["image"], new["imageAlt"]), (target, "Lemons"))
        site = chat.kit.wt / "storefront-mockup"
        self.assertTrue((site / old["image"]).is_file())  # the old picture file stays
        chat.say("undo")
        chat.say(f"yes {chat.drafts()[-1]['code']}")
        back = chat.lemons()
        self.assertEqual((back.get("image"), back.get("imageAlt")), (old.get("image"), old.get("imageAlt")))
        self.assertTrue((site / target).is_file())  # the declared residue: the new photo file stays, unused
        self.assertTrue((site / old["image"]).is_file())

    def test_flag_on_installer_retake_is_item_add_parity_and_good_render_is_byte_identical(self):
        chat = self.open(BUSY, JAR, house_render=True)
        d, r = chat.say("new picture for the lemons", {"item": "Lemons"}, BUSY)
        self.assertNotEqual(d, "proposed")  # the installer will not stand behind it: nothing drafted, nothing installed
        self.assertIn("nothing changed", r)  # the conversation's own sentence for an installer refusal, as for item.add
        self.assertEqual((chat.drafts(), chat.head()), ([], chat.base))
        self.assertFalse((chat.kit.wt / "storefront-mockup" / f"assets/products/photo-{SHA[BUSY][:16]}.jpg").exists())
        d, r = chat.say("here is a better one of the lemons", {"item": "Lemons"}, JAR)
        self.assertEqual(d, "proposed")
        self.assertIn(item_add.PICTURE_OK, r)
        chat.say(f"yes {chat.drafts()[-1]['code']}")
        target = f"assets/products/photo-{SHA[JAR][:16]}.jpg"
        self.assertEqual(chat.lemons()["image"], target)
        web = photos._web_bytes(chat.kit.media_root, SHA[JAR])[0]
        self.assertEqual((chat.kit.wt / "storefront-mockup" / target).read_bytes(), photos.house_picture(web)["jpeg"])

    def test_draft_is_outside_the_live_boundary(self):
        chat = self.open(JAR)
        plan = ip.plan_picture({"item": LEMONS, "photo": SHA[JAR]}, chat.kit._ctx())
        out = chat.kit.editor.prepare(plan)
        self.assertEqual(out["result"], "ok", out)
        self.assertNotEqual(live_policy.check(out["draft"]), [])  # private-only: product.set_photo is not live


if __name__ == "__main__":
    unittest.main()
