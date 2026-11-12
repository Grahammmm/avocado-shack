"""RF1721-11: an explicit Unicode product-name answer settles the one-photo question of item.picture.

A saved name with no ASCII selection word (``_words`` is empty) could never be chosen after a crowded photo request. These
tests use local synthetic products and photo ids only; nothing is read, written or sent.
Run: python3 -B -m unittest hass.tests.test_item_picture_unicode_choice -v
"""
import copy
import unicodedata
import unittest
from types import SimpleNamespace

from hass import voice
from hass.content_model import REPO_ROOT, load_and_validate
from hass.skills import item_picture as ip

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
LEMONS, HELD, PLUMS = "photo-product-017", "photo-product-040", "photo-product-031"
PHOTO = "ab" * 32
CROWDED = "use this photo for both of them"
HOME = "use this photo for the home page and the product"
NFC_ACAI, NFD_ACAI = "A\u00e7a\u00ed", unicodedata.normalize("NFD", "A\u00e7a\u00ed")


def named(pid, name, **fields):
    content = copy.deepcopy(CONTENT)
    next(p for p in content.products if p["id"] == pid).update(name=name, **fields)
    return content


def ctx(content, *texts):
    return SimpleNamespace(today="2026-11-08", content=content, texts=list(texts))


def slots(pid=LEMONS, alt="Photo of the product"):
    return {"item": pid, "photo": PHOTO, "image_alt": alt}


def asks(content, *texts, **kw):
    with unittest.TestCase().assertRaises(ip.Refusal) as caught:
        ip.plan_picture(slots(**kw), ctx(content, *texts))
    return caught.exception


class UnicodeChoice(unittest.TestCase):
    def assertSettles(self, content, *texts, pid=LEMONS):
        out = ip.plan_picture(slots(pid), ctx(content, *texts))
        self.assertEqual(out, [{"op": "product.set_photo", "args": {"id": pid, "photo": PHOTO, "imageAlt": "Photo of the product"}}])

    def test_exact_unicode_name_settles_crowded_photo_question(self):
        for name in ("柚子", "茶", NFC_ACAI):
            content = named(LEMONS, name)
            self.assertEqual(ip._words(name), set())  # the premise: no ASCII selection word survives
            with self.subTest(name=name):
                self.assertEqual(asks(content, CROWDED).reply, ip.ONE_AT_A_TIME)
                self.assertSettles(content, CROWDED, name)
                self.assertSettles(content, CROWDED, f"the {name} please")
                self.assertSettles(content, CROWDED, f"yes, {name}")
                self.assertEqual(asks(named(LEMONS, name), HOME).reply, ip.ONE_PLACE)
                self.assertSettles(content, HOME, f"it's the {name}")

    def test_unicode_choice_requires_name_not_unrelated_answer(self):
        content = named(LEMONS, "茶")
        for answer in ("", "yes", "ok", "柚子", "红茶", "茶叶", "茶茶", "tea"):
            with self.subTest(answer=answer):
                self.assertEqual(asks(content, CROWDED, answer).reply, ip.ONE_AT_A_TIME)
        content = named(LEMONS, NFC_ACAI)
        for answer in ("Acai", "A\u00e7a", "A\u00e7a\u00edx", "xA\u00e7a\u00ed"):
            with self.subTest(answer=answer):
                self.assertEqual(asks(content, CROWDED, answer).reply, ip.ONE_AT_A_TIME)
        self.assertEqual(asks(named(LEMONS, "柚子"), HOME, "the plums").reply, ip.ONE_PLACE)

    def test_unicode_rejection_and_latest_answer_policy(self):
        content = named(LEMONS, "柚子")
        for answer in ("not 柚子", "not the 柚子", "anything but 柚子", "other than 柚子", "the plums instead of 柚子",
                       "柚子 isn't it", "柚子 is not the one", "柚子 is definitely not the one", "柚子 aren't"):
            with self.subTest(answer=answer):
                self.assertEqual(asks(content, CROWDED, answer).reply, ip.ONE_AT_A_TIME)
        self.assertEqual(asks(content, CROWDED, "柚子", "not 柚子").reply, ip.ONE_AT_A_TIME)  # a later no wins
        self.assertSettles(content, CROWDED, "not 柚子", "柚子")  # a later yes corrects it
        self.assertSettles(content, CROWDED, "not the plums, 柚子")  # a clause rejecting another product
        self.assertEqual(asks(content, CROWDED, "the plums, not 柚子").reply, ip.ONE_AT_A_TIME)

    def test_nfc_equivalent_accented_answer_is_comparison_only(self):
        for saved, said in ((NFC_ACAI, NFD_ACAI), (NFD_ACAI, NFC_ACAI), (NFC_ACAI, NFC_ACAI.upper())):
            content = named(LEMONS, saved)
            texts = (CROWDED, f"the {said}")
            before = copy.deepcopy(texts)
            with self.subTest(saved=saved, said=said):
                self.assertSettles(content, *texts)
                self.assertEqual(texts, before)
                self.assertEqual(next(p for p in content.products if p["id"] == LEMONS)["name"], saved)
        self.assertEqual(asks(named(LEMONS, NFC_ACAI), CROWDED, f"not {NFD_ACAI}").reply, ip.ONE_AT_A_TIME)

    def test_ascii_and_multiplace_guards_unchanged(self):
        self.assertSettles(CONTENT, "photos for lemons and plums", "the lemons please")
        self.assertEqual(asks(CONTENT, "photos for lemons and plums", "not the lemons").reply, ip.ONE_AT_A_TIME)
        self.assertEqual(asks(CONTENT, "photos for lemons and plums", "the plums").reply, ip.ONE_AT_A_TIME)
        self.assertEqual(asks(CONTENT, "photos for lemons and plums", "lemons and plums").reply, ip.ONE_AT_A_TIME)
        self.assertSettles(CONTENT, "photos for lemons and plums", "photos for lemons and plums", "lemons")
        self.assertEqual(asks(CONTENT, "photos for lemons and plums", "photos for lemons and plums").reply, ip.ONE_AT_A_TIME)
        self.assertEqual(asks(CONTENT, "use this photo for the lemons and the home page").reply, ip.ONE_PLACE)
        self.assertEqual(asks(CONTENT, "use this photo for the lemons and the home page", "not the lemons").reply, ip.ONE_PLACE)
        # a Unicode name in a list is still two products; a list answer is not the one product
        content = named(LEMONS, "柚子")
        self.assertEqual(asks(content, "photos for 柚子 and plums").reply, ip.ONE_AT_A_TIME)
        self.assertEqual(asks(content, CROWDED, "柚子 and plums").reply, ip.ONE_AT_A_TIME)
        # an ASCII name keeps its ASCII path: a Unicode token near it does not matter
        self.assertSettles(CONTENT, CROWDED, "lemons 柚子")
        self.assertEqual(ip._words("Lemons"), {"lemon"})
        self.assertEqual(ip._picks("the lemons", {"lemon"}), True)
        self.assertEqual(ip._picks("anything", set()), None)

    def test_plan_does_not_write_or_bypass_other_refusals(self):
        content = named(LEMONS, "柚子")
        snapshot, texts = copy.deepcopy(content.products), [CROWDED, "柚子"]
        given = slots()
        before = copy.deepcopy(given)
        ip.plan_picture(given, ctx(content, *texts))
        self.assertEqual(given, before)
        self.assertEqual(texts, [CROWDED, "柚子"])
        self.assertEqual(content.products, snapshot)
        held = named(LEMONS, "柚子", status="held")
        self.assertIn("on hold", voice.plain(asks(held, CROWDED, "柚子").reply))
        hidden = named(LEMONS, "柚子", status="hidden")
        self.assertIn("is hidden", voice.plain(asks(hidden, CROWDED, "柚子").reply))
        with self.assertRaises(ip.Refusal) as caught:
            ip.plan_picture({"item": LEMONS}, ctx(content, CROWDED, "柚子"))
        self.assertEqual(caught.exception.reply, ip.ASK_PHOTO)
        same = named(LEMONS, "柚子", image=ip.installed_names(PHOTO)[0])
        with self.assertRaises(ip.Refusal) as caught:
            ip.plan_picture(slots(), ctx(same, CROWDED, "柚子"))
        self.assertIn("already has this photo", caught.exception.reply)


if __name__ == "__main__":
    unittest.main()
