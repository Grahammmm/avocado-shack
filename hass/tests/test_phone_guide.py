"""AV2022-14 (H25): every message docs/hass/PHONE_GUIDE.md tells the owner to send parses as it claims. Stdlib, offline."""
import re
import unittest
from pathlib import Path

from hass import conversation as conv
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_margin_chat import USAGE, steps
from hass.tests.test_near_approval import TextInterpreter
from hass.tests.test_status_pause import StoreMixin
from hass.tests.test_undo import H06TestCase

DOCS = Path(__file__).resolve().parents[2] / "docs" / "hass"
SECTIONS = ["Add a product", "Add a photo", "Post a hike", "Change opening hours", "Change the home page", "Route ideas", "Undo a change", "Pause and resume"]
SEND_RE = re.compile(r"Send(?: \((plain words|decorated yes|code only)\))?: `([^`]+)`")  # AV1352-11: two typed reply kinds beside plain words
KINDS = {"decorated yes": ("approve", "a1b2"), "code only": (None, "a1b2")}  # label -> what conv.parse_phone must read from the example
MARGIN_PRICE, MARGIN_ENDING = "margin 24 for 12 price 3.49", "margin 24 for 12 at 35% ending .99"
AV1352_SENDS = (("decorated yes", "Yes, a1b2 thanks"), ("code only", "a1b2"), (False, "status?"), (False, "find eggs?"), (False, "remember parking spot: use the back lot"),
                (False, "forget parking spot"), (False, MARGIN_PRICE), (False, MARGIN_ENDING))
AV1352_EXPLAINS = {  # AV1352-11: each safety clause once; dropping or rewording any one is named
    "decorated yes names its draft": "it approves only the draft that code names", "code alone changes nothing": "The code alone changes nothing",
    "code alone is a hint": "it is a hint, never an approval", "? never approves or undoes": "`yes a1b2?` approves nothing and `undo a1b2?` undoes nothing",
    "? is for read-only commands": "A closing `?` works on read-only commands", "spaces become hyphens": "Spaces in the name become `-`, so `parking spot` is kept as `parking-spot`",
    "margins are private": "they save nothing and put no price on the website", "ending never rounds down": "never lower than the margin needs",
    "illustration warning": "the `post` reply starts with a warning that the picture is not a photo of the product", "owner photo exception": "an owner photo gets no warning",
    "post reply carries the photo": "a draft caption and, when the product has an eligible site photo, that photo as an attachment (the illustration or the owner photo alike)",
    "post publishes nothing": "Hass posts or uploads nothing to any social account", "hike and maker are text only": "`post hike` and `post maker` come back as text only"}
STALE_POST_CLAIMS = ("only a draft caption comes back", "nothing is uploaded, sent or published")  # AV1352-11 RETURN: the product reply attaches the photo (reports_pack._post)
NEW_EXAMPLES = {"hide the sample hikes", "bring the sample hikes back", "put the old photo back", "stop showing the eggs as sold out"}  # AV1622-11
LISTING = "listing photo-product-001"
AV1937_PLAIN = (
    "Use this for the home page, a crate of ripe avocados on the counter",
    "Add a new maker called Example Orchard and its first product, pear jam",
    "Add a maker called Example Orchard; it has no website",
    "Stop stocking Example Orchard and hide its products",
    "Repeat hike walk-001 on 2026-12-06 at 09:00",
)  # AV1937-13
AV1937_POST = "post maker Example Orchard"
AV2152_PLAIN = (
    "For draft a1b2, use this on the home page: avocados in a wooden crate",
    "Cancel hike walk-001 with the note: Rained out - we will pick a new date soon.",
    "Set the hiking club opening paragraph to: Walk with us along the coast, share the trail, and leave room for discovery.",
    "Set the home notice to \"Closed Thanksgiving Day\" from 2026-11-26 through 2026-11-26.",
)
AV2152_COMMANDS = {"history notice": "history", "again a1b2": "again"}  # AV2152-14
AV0222_EXAMPLES = (  # AV0222-12: (plain words?, text)
    (True, "Make the green jam sold out"), (True, "Add Test Orchard quince, brand Test Orchard"),
    (True, "Add a maker called Test Orchard, with no story"), (True, "thanks"), (True, "\U0001f44d"),
    (True, "Set the quince price to $3"), (False, "photos to take"), (False, "undo that"), (False, "never mind"))
AV0222_VERBS = {"photos to take": "photos", "undo that": "undo", "never mind": "reject"}
AV0222_EXPLAINS = {  # one phrase per owner explanation; dropping any one is reported by name
    "one brand": "needs one brand, not a second card brand", "alias adds no facts": "naming it adds no facts",
    "no invented story": "A maker may have no story: Hass never invents one", "thanks changes nothing": "`thanks` makes no change",
    "thumbs-up is not approval": "a thumbs-up is not an approval", "price draft refused": "nothing is drafted for a price-only change",
    "photos list is saved only": "saved active products that still use a catalog picture", "photos not a live check": "not a live-site or photo-authenticity check",
    "history approved in Pacific": "when a change was approved, in Pacific time", "history time unknown": "`time unknown`",
    "undo that needs a new yes": "needs its own new `yes` code", "never mind is not an undo": "cancels a waiting draft or question without undoing anything",
    "ambiguity asks": "Hass asks instead of guessing"}
LINE_CAP = 110
AV1052_PLAIN = ("All the vegetables are in today", "Everything from Cal Poly is sold out", "histroy", "Make the product cards round")  # AV1052-15
AV1052_VERBS = {"shelf vegetables": "shelf", "listing store": "listing", "post sourdough": "post", "listing sourdough": "listing",
                "no all": "reject", "help undo": "help", "memory": "memory"}
AV1052_EXPLAINS = {  # one phrase per safety clause; dropping or weakening any one is reported by name
    "bulk is one draft": "Hass makes one draft for the changed active products in it", "bulk needs its one code": "approve its one code",
    "bulk leaves hidden and held": "Hidden and held products stay out", "bulk keeps the shelf-check date": "the shelf-check date does not change",
    "bulk is not live stock": "does not promise live stock or approve it for you", "reads are saved not live": "read saved data (not a live check of the website)",
    "post never publishes": "only prepares a caption or photo and never publishes", "name needs one unique match": "needs one unique active match",
    "no all keeps photos": "cancels every waiting draft and question, keeps stored photos and changes nothing on the website",
    "approval keeps its own code": "each approval still needs its own code", "yes all refused": "`yes all` is refused",
    "typo gets a guess only": "gets only a guess and nothing runs", "typo reply is literal": "`Did you mean history? Send history.`",
    "typo is resent whole": "send `history` again as a whole message", "failed read says why": "could not read a written request (the reader was not working), nothing was drafted",
    "failed read is resent": "send that change again once it is back", "no automatic retry": "does not retry by itself",
    # AV1052-15 review: a failed photo caption leaves a needs-details draft (core_pack._reader_failed_lines), so "nothing was drafted /
    # send it again" is true only for written requests; a doc that tells photo owners to resend would loop on "duplicate"
    "failed photo keeps its draft": "keeps the photo as a draft waiting for details", "failed photo is answered by reply": "reply with the product and what the photo shows",
    "resent photo is a duplicate": "Sending the same photo again is refused as a duplicate and its caption is not read",
    "expired photo is resent": "If status says the photo's time ran out, send the photo again with its caption",
    "design note is local": "kept on the shop computer as a design note for the developer",
    "design note is not a preference": "neither sent nor used as a preference", "design note is forgotten by key": "`forget design.<n>`"}
PRIVATE_RE = re.compile(r"[\w.+-]+@[\w-]+\.\w+|\+\d|http://", re.I)


def route(text):
    """AV1352-11: the verb a whole message reads as: the plain parsers, then the read-only `?` and memory readers the conversation also tries."""
    return verb(text) or next((r[0] for r in (conv.read_command(text), conv.read_memory(text)) if r), None)


def sends(doc: str) -> list:
    """(kind, text, line) for each quoted message; kind is True for plain words, False for a command, or the typed reply label.
    A line naming Send that breaks the convention gives text None."""
    out = []
    for line in doc.splitlines():
        if not re.match(r"\s*Send\b", line):
            continue
        m = SEND_RE.fullmatch(line.strip())
        out.append(((m[1] == "plain words" or m[1]) if m and m[1] else False, m[2] if m else None, line.strip()))
    return out


def reads_as(kind: str, text: str) -> bool:
    """AV1352-11: the typed reply parses the way its label says: a whole-message coded answer, never a command."""
    got = conv.parse_phone(text)
    return got is not None and got[0] == KINDS[kind][0] and re.fullmatch(r"[0-9a-f]{4}", got[1] or "") is not None and not got[2] and route(text) is None


def problems(doc: str) -> list:
    out = []
    for plain, text, line in sends(doc):
        if text is None:
            out.append(f"not a Send line the checker can read: {line}")
        elif isinstance(plain, str) and plain != "plain words":
            if not reads_as(plain, text):
                out.append(f"Send ({plain}) line does not read as that kind of reply: {line}")
        elif plain and route(text) is not None:
            out.append(f"plain-words line parses as a command ({route(text)}): {line}")
        elif not plain and route(text) is None:
            out.append(f"Send line is not a command: {line}")
    found = {(plain, text) for plain, text, _ in sends(doc)}
    out += [f"required example missing or misclassified: {t}" for k, t in AV1352_SENDS if (k, t) not in found]
    out += [f"required explanation missing ({name}): {text}" for name, text in AV1352_EXPLAINS.items() if text not in doc]
    out += [f"required example missing or misclassified: {t}" for t in AV1937_PLAIN if (True, t) not in found]
    out += [f"required example missing or misclassified: {AV1937_POST}"] if (False, AV1937_POST) not in found else []
    out += [f"required example missing or misclassified: {t}" for t in AV2152_PLAIN if (True, t) not in found]
    out += [f"required example missing or misclassified: {t}" for t in AV2152_COMMANDS if (False, t) not in found]
    out += [f"required example missing or misclassified: {t}" for plain, t in AV0222_EXAMPLES if (plain, t) not in found]
    out += [f"required explanation missing ({name}): {text}" for name, text in AV0222_EXPLAINS.items() if text not in doc]
    out += [f"required example missing or misclassified: {t}" for t in AV1052_PLAIN if (True, t) not in found]
    out += [f"required example missing or misclassified: {t}" for t in AV1052_VERBS if (False, t) not in found]
    out += [f"required explanation missing ({name}): {text}" for name, text in AV1052_EXPLAINS.items() if text not in doc]
    headings = re.findall(r"^## (.+)$", doc, re.M)
    if headings != SECTIONS:
        out.append(f"sections are {headings}, not {SECTIONS}")
    out += [f"private text or http link: {ln.strip()}" for ln in doc.splitlines() if PRIVATE_RE.search(ln)]
    return out


class PhoneGuideTest(unittest.TestCase):
    def setUp(self):
        self.doc = (DOCS / "PHONE_GUIDE.md").read_text("utf-8")

    def test_guide_is_clean_and_short(self):
        self.assertEqual(problems(self.doc), [])
        self.assertLessEqual(len(self.doc.splitlines()), 110)

    def test_core_commands_quoted_and_plain_words_present(self):
        commands = {text for plain, text, _ in sends(self.doc) if not plain}
        self.assertLessEqual({"yes a1b2", "undo a1b2", "history", "pause changes", "resume changes", "status"}, commands)
        self.assertTrue(any(plain for plain, _, _ in sends(self.doc)), "no plain-words example")

    def test_new_examples_required_and_classified(self):  # AV1622-11
        found = sends(self.doc)
        plain = {text for p, text, _ in found if p}
        commands = {text for p, text, _ in found if not p}
        self.assertLessEqual(NEW_EXAMPLES, plain)
        self.assertIn(LISTING, commands)
        self.assertEqual(verb(LISTING), "listing")
        for text in NEW_EXAMPLES:
            self.assertIsNone(verb(text), text)
        for text in sorted(NEW_EXAMPLES):  # dropping any one is caught
            self.assertNotIn(text, {t for _p, t, _l in sends(self.doc.replace(f"`{text}`", "`gone`"))})
        self.assertEqual(problems(self.doc.replace("Send: `listing photo-product-001`", "Send (plain words): `listing photo-product-001`"))[0][:36],
                         "plain-words line parses as a command")

    def test_av1937_examples_required_and_classified(self):  # AV1937-13
        found = sends(self.doc)
        self.assertLessEqual(set(AV1937_PLAIN), {t for p, t, _ in found if p})
        self.assertIn(AV1937_POST, {t for p, t, _ in found if not p})
        for text in AV1937_PLAIN:
            self.assertIsNone(verb(text), text)
        self.assertEqual(verb(AV1937_POST), "post")
        self.assertEqual(problems(self.doc), [])

    def test_missing_or_reclassified_av1937_example_fails(self):  # AV1937-13
        for text in (*AV1937_PLAIN, AV1937_POST):
            missing = f"required example missing or misclassified: {text}"
            plain = text in AV1937_PLAIN
            line = f"Send{' (plain words)' if plain else ''}: `{text}`"
            self.assertIn(line, self.doc)
            self.assertEqual(problems(self.doc.replace(f"`{text}`", "`gone`")), [f"Send line is not a command: Send: `gone`", missing] if not plain else [missing])
            flipped = f"Send{'' if plain else ' (plain words)'}: `{text}`"
            self.assertIn(missing, problems(self.doc.replace(line, flipped)), text)

    def test_photo_reply_is_not_an_approval(self):  # AV1937-13
        photo = AV1937_PLAIN[0]
        self.assertIsNone(verb(photo))
        self.assertEqual(verb("yes a1b2"), "approve")
        self.assertIn(f"Send (plain words): `{photo}`", self.doc)
        self.assertIn("send any `yes` as its own message", self.doc)

    def test_non_command_send_line_fails(self):
        self.assertEqual(problems(self.doc + "Send: `yes please`\n"), ["Send line is not a command: Send: `yes please`"])

    def test_command_as_plain_words_fails(self):
        bad = "Send (plain words): `history`"
        self.assertEqual(problems(self.doc + bad + "\n"), [f"plain-words line parses as a command (history): {bad}"])

    def test_off_convention_send_line_fails(self):
        for bad in ("Send: yes a1b2", "Send `status` now", "Send (plain words) `Add jam`", "Send: `status` and `history`"):
            self.assertEqual(problems(self.doc + bad + "\n"), [f"not a Send line the checker can read: {bad}"], bad)

    def test_sections_missing_extra_or_reordered_fail(self):
        swapped = self.doc.replace("## Undo a change", "## TMP").replace("## Pause and resume", "## Undo a change")
        swapped = swapped.replace("## TMP", "## Pause and resume")
        for doc in (swapped, self.doc.replace("## Post a hike", "## Post hikes"), self.doc + "## Extra\n"):
            self.assertEqual(len(problems(doc)), 1)
            self.assertTrue(problems(doc)[0].startswith("sections are"))

    def test_private_text_fails(self):
        for bad in ("Mail owner@example.com", "Call +15551234567", "See http://example.com"):
            self.assertEqual(problems(self.doc + bad + "\n"), [f"private text or http link: {bad}"], bad)
        self.assertEqual(problems(self.doc + "See [limits](LIMITS.md) or https://example.com\n"), [])

    def test_av2152_examples_required_and_classified(self):  # AV2152-14
        found = sends(self.doc)
        self.assertLessEqual(set(AV2152_PLAIN), {t for p, t, _ in found if p})
        self.assertLessEqual(set(AV2152_COMMANDS), {t for p, t, _ in found if not p})
        for text in AV2152_PLAIN:
            self.assertIsNone(verb(text), text)
        for text, name in AV2152_COMMANDS.items():
            self.assertEqual(verb(text), name)
        self.assertEqual(problems(self.doc), [])

    def test_av2152_missing_or_reclassified_example_fails(self):  # AV2152-14
        for text in (*AV2152_PLAIN, *AV2152_COMMANDS):
            plain = text in AV2152_PLAIN
            missing = f"required example missing or misclassified: {text}"
            line = f"Send{' (plain words)' if plain else ''}: `{text}`"
            self.assertIn(line, self.doc)
            self.assertIn(missing, problems(self.doc.replace(f"`{text}`", "`gone`")), text)
            flipped = f"Send{'' if plain else ' (plain words)'}: `{text}`"
            self.assertIn(missing, problems(self.doc.replace(line, flipped)), text)

    def test_batch_photo_instructions_and_separate_codes(self):  # AV2152-14
        for text in ("one to four photos in one message", "Each newly accepted photo gets its own draft code",
                     "already waiting, repeated in the same message, or already on a product", "does not get a new draft code",
                     "none is saved", "caption on several photos is ignored", "repeat the answer for each actual code",
                     "separately with its own code", "no text command that sends photos"):
            self.assertIn(text, self.doc)
            self.assertNotIn(text, self.doc.replace(text, ""), text)
        self.assertNotRegex(self.doc, r"(?i)one photo per message")

    def test_again_window_and_named_approval_wording(self):  # AV2152-14
        step = next(l for l in self.doc.splitlines() if "expired within the last seven days" in l)
        for text in ("site still matches", "new code and expiry", "separately with `yes` and the new code",
                     "A photo, a question, a cancelled, replaced or applied draft is not renewed"):
            self.assertIn(text, step)
        self.assertIn("resuming never applies a waiting draft by itself", self.doc)

    def test_store_undo_keeps_other_fields_not_same_field(self):  # AV2152-14
        for text in ("keeping a later shelf check or other detail", "a later edit of the same detail is a conflict and the undo is refused",
                     "with its new code", "Not every older change can be undone"):
            self.assertIn(text, self.doc)
            self.assertNotIn(text, self.doc.replace(text, ""), text)

    def test_notice_and_club_wording_promises_nothing_outbound(self):  # AV2152-14
        for text in ("Before the first day it stays hidden", "Hass sends no message to guests", "guests are not messaged",
                     "club page copy only, still a draft you approve; it is not an announcement or the store intro"):
            self.assertIn(text, self.doc)

    def test_readme_links_the_guide(self):
        self.assertIn("](PHONE_GUIDE.md)", (DOCS / "README.md").read_text("utf-8"))


    def test_av0222_examples_present_and_routed(self):  # AV0222-12
        from hass.social_message import classify_social
        found = {(p, t) for p, t, _ in sends(self.doc)}
        self.assertLessEqual(set(AV0222_EXAMPLES), found)
        for text, name in AV0222_VERBS.items():
            self.assertEqual(verb(text), name)
        for plain, text in AV0222_EXAMPLES:
            if plain:
                self.assertIsNone(verb(text), text)
        self.assertEqual((classify_social("thanks"), classify_social("\U0001f44d")), ("social", "near"))
        self.assertIsNone(classify_social("Set the quince price to $3"))
        from hass.interpret_check import PRICE_REPLY
        self.assertIn("doesn't show prices", PRICE_REPLY)  # the doc's price sentence follows the shared reply
        self.assertIn("without the price", PRICE_REPLY)
        self.assertEqual(problems(self.doc), [])
        self.assertLessEqual(len(self.doc.splitlines()), 110)

    def test_missing_or_reclassified_new_example_fails(self):  # AV0222-12
        for plain, text in AV0222_EXAMPLES:
            missing = f"required example missing or misclassified: {text}"
            line = f"Send{' (plain words)' if plain else ''}: `{text}`"
            self.assertIn(line, self.doc)
            self.assertIn(missing, problems(self.doc.replace(f"`{text}`", "`gone`")), text)
            flipped = f"Send{'' if plain else ' (plain words)'}: `{text}`"
            self.assertIn(missing, problems(self.doc.replace(line, flipped)), text)

    def test_owner_explanations_do_not_promise_apply(self):  # AV0222-12
        for name, text in AV0222_EXPLAINS.items():
            self.assertEqual(self.doc.count(text), 1, text)
            self.assertEqual(problems(self.doc.replace(text, "gone")), [f"required explanation missing ({name}): {text}"], name)

    def test_av1052_examples_are_present_and_routed(self):  # AV1052-15: an owner can copy each new shortcut and it parses as the guide says
        found = {(p, t) for p, t, _ in sends(self.doc)}
        self.assertLessEqual({(True, t) for t in AV1052_PLAIN} | {(False, t) for t in AV1052_VERBS}, found)
        for text in AV1052_PLAIN:
            self.assertIsNone(verb(text), text)  # bulk, typo and layout sentences are plain words, never a command
        for text, name in AV1052_VERBS.items():
            self.assertEqual(verb(text), name, text)
        self.assertEqual(problems(self.doc), [])

    def test_missing_reclassified_examples_and_111_lines_fail(self):  # AV1052-15: each drift names the example, not just "something broke"
        for plain, text in [(True, t) for t in AV1052_PLAIN] + [(False, t) for t in AV1052_VERBS]:
            missing = f"required example missing or misclassified: {text}"
            line = f"Send{' (plain words)' if plain else ''}: `{text}`"
            self.assertIn(line, self.doc)
            self.assertIn(missing, problems(self.doc.replace(f"`{text}`", "`gone`")), text)
            self.assertIn(missing, problems(self.doc.replace(line, f"Send{'' if plain else ' (plain words)'}: `{text}`")), text)
        self.assertLessEqual(len(self.doc.splitlines()), LINE_CAP)
        self.assertGreater(len((self.doc + "One more line.\n" * (LINE_CAP + 1 - len(self.doc.splitlines()))).splitlines()), LINE_CAP)  # the 111th line is over
        for bad in ("Send: `shelf vegetables` and `listing store`", "Mail owner@example.com"):
            self.assertNotEqual(problems(self.doc + bad + "\n"), [], bad)

    def test_explanations_never_promise_apply_publish_or_retry(self):  # AV1052-15: the safety clauses cannot be dropped or reworded away
        for name, text in AV1052_EXPLAINS.items():
            self.assertEqual(self.doc.count(text), 1, text)
            self.assertEqual(problems(self.doc.replace(text, "gone")), [f"required explanation missing ({name}): {text}"], name)
        for promise in (r"(?i)\bautomatically (?:approve|apply|publish|retr)", r"(?i)\bposts? (?:it )?to the website\b"):
            self.assertNotRegex(self.doc, promise)


class GuideCodeTests(H06TestCase):  # AV1352-11: the two taught coded replies, against a real waiting draft
    def setUp(self):
        super().setUp()
        self.interp = TextInterpreter(self.interp.mapping)
        self.conv = self.open()
        self.doc = (DOCS / "PHONE_GUIDE.md").read_text("utf-8")

    def taught(self, kind):
        [text] = [t for k, t, _ in sends(self.doc) if k == kind]
        return text

    def test_decorated_yes_approves_only_its_draft_and_code_alone_changes_nothing(self):
        a, b = self.propose("hours")[0], self.propose("desc")[0]
        self.replies()
        alone = self.taught("code only").replace("a1b2", a["code"])
        self.assertEqual(self.say(alone), "near-approval")
        self.assertEqual(self.replies(), [f"I haven't changed anything yet. To go ahead, reply yes {a['code']}, or no {a['code']} to cancel."])
        self.assertEqual(self.say(f"yes {a['code']}?"), "near-approval")
        self.replies()
        approvals = lambda: self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        self.assertEqual((approvals(), self.commits(), {d["code"]: d["state"] for d in self.drafts()}[a["code"]]), (0, 0, "proposed"))
        self.assertEqual(self.say(self.taught("decorated yes").replace("a1b2", a["code"])), "approved")
        states = {d["code"]: d["state"] for d in self.drafts()}
        self.assertEqual((approvals(), states[b["code"]]), (1, "proposed"))
        self.assertNotEqual(states[a["code"]], "proposed")

    def test_unknown_code_is_not_approved(self):
        self.propose("hours")
        self.replies()
        self.say(self.taught("decorated yes").replace("a1b2", "ffff"))  # not a waiting code: never approves anything
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)


class GuideMarginTests(StoreMixin, ConversationTestCase):  # AV1352-11: each taught margin line reaches its own calculation
    def setUp(self):
        super().setUp()
        self.conv = self.open()

    def margin(self, text):
        self.assertEqual(self.say(text), "margin")
        [reply] = self.replies()
        return reply

    def test_price_check_and_rounded_ending_lines_reach_their_modes(self):
        from hass import margins
        before = (self.drafts(), self.commits(), self.approvals())
        price = self.margin(MARGIN_PRICE)
        self.assertIn(steps("24", "12", "0", "3.49"), price)
        self.assertIn("Your margin", price)
        ending = self.margin(MARGIN_ENDING)
        self.assertEqual(ending, margins.say(margins.compute("24", "12", "0", "35", ".99")))
        self.assertIn("Charge $3.99.", ending)  # 35% needs about $3.08; rounded up to .99, not down to $2.99
        self.assertNotEqual((price, ending), (USAGE, USAGE))
        self.assertEqual((self.drafts(), self.commits(), self.approvals()), before)  # a private estimate saves and approves nothing
        for bad in (MARGIN_PRICE + " ending .99", MARGIN_ENDING.replace("ending", "price"), MARGIN_ENDING.replace(".99", "0.99")):
            self.assertEqual(self.margin(bad), USAGE, bad)


class AV1352Test(unittest.TestCase):
    def setUp(self):
        self.doc = (DOCS / "PHONE_GUIDE.md").read_text("utf-8")

    def test_examples_are_present_and_route_as_taught(self):
        found = {(k, t) for k, t, _ in sends(self.doc)}
        self.assertLessEqual(set(AV1352_SENDS), found)
        self.assertEqual((route("status?"), conv.read_command("find eggs?")), ("status", ("find", "eggs")))  # the ? is not part of the query
        self.assertEqual(conv.parse_memory("remember parking spot: use the back lot"), ("remember", "parking-spot", "use the back lot"))
        self.assertEqual(conv.parse_memory("forget parking spot"), ("forget", "parking-spot", None))
        for text in ("yes a1b2?", "undo a1b2?"):  # the ? never turns a write into a read
            self.assertIsNone(route(text), text)
        self.assertEqual(problems(self.doc), [])
        self.assertLessEqual(len(self.doc.splitlines()), LINE_CAP)

    def test_post_wording_matches_what_the_reply_sends(self):
        """Contract: the guide says the product `post` reply carries the eligible photo, yet publishes nothing. Bug caught: the guide denying the attachment."""
        for stale in STALE_POST_CLAIMS:
            self.assertNotIn(stale, self.doc)
            self.assertIn(f"required explanation missing (post reply carries the photo): {AV1352_EXPLAINS['post reply carries the photo']}", problems(self.doc.replace(AV1352_EXPLAINS["post reply carries the photo"], stale)))
        self.assertNotRegex(self.doc, r"(?i)\bnothing is [^.]*\bsent\b")

    def test_illustration_wording_follows_the_post_warning(self):
        from hass.chat import reports_pack
        self.assertIn("illustration", reports_pack.POST_ILLUSTRATION)
        self.assertIn("not a photo of the product", reports_pack.POST_ILLUSTRATION)

    def test_missing_mislabelled_or_reworded_lines_fail_by_name(self):
        for kind, text in AV1352_SENDS:
            missing = f"required example missing or misclassified: {text}"
            line = next(l for k, t, l in sends(self.doc) if (k, t) == (kind, text))
            self.assertIn(missing, problems(self.doc.replace(line, line.replace(f"`{text}`", "`gone`"))), text)
            flipped = "Send: " if isinstance(kind, str) else "Send (code only): "
            self.assertIn(missing, problems(self.doc.replace(line, flipped + f"`{text}`")), text)
        for name, text in AV1352_EXPLAINS.items():
            self.assertEqual(self.doc.count(text), 1, text)
            self.assertIn(f"required explanation missing ({name}): {text}", problems(self.doc.replace(text, "gone")))

    def test_typed_replies_cannot_be_faked(self):
        for line in ("Send (code only): `Yes, a1b2 thanks`", "Send (decorated yes): `a1b2`", "Send (code only): `a1b2?`", "Send (decorated yes): `yes a1b2 a1b3`",
                     "Send (code only): `status`", "Send (decorated yes): `yes a1b2?`", "Send (code only): `hello`"):
            self.assertNotEqual(problems(self.doc + line + "\n"), [], line)
        self.assertEqual(problems(self.doc + "Send (decorated yes): `ok, approve a1b2 thank you!`\n"), [])
        self.assertIn("not a Send line", problems(self.doc + "Send (hint): `a1b2`\n")[0])
        self.assertIn("plain-words line parses as a command", problems(self.doc + "Send (plain words): `status?`\n")[0])


if __name__ == "__main__":
    unittest.main()
