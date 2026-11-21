"""HRM-05: an offline baseline for S10, not a list of desired parser changes."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import unittest
from unittest.mock import Mock

from hass.npp import assets, edits


MAPPER = "mapper"
UNCLEAR = "unclear"
GENERIC_ASK = edits.Edit(ask="ask_edit_unclear")
ASK_PRICE = edits.Edit(ask="ask_price")
PICTURE = edits.Edit(reply="picture_request")
REWRITE = edits.Edit(patch=(("rewrite", "description"),))


@dataclass(frozen=True)
class Phrase:
    text: str
    expected: edits.Edit | str
    price: str | None = None
    sold_by: str | None = None
    remainder: str | None = None
    explicit_value: tuple[str, str] | None = None

    def read(self, grammar, mapper=None):
        text = self.text if self.remainder is None else self.remainder
        finance = {"price": self.price, "sold_by": self.sold_by}
        return edits.read(grammar, text, finance, mapper=mapper)

    @property
    def bucket(self):
        if isinstance(self.expected, str):
            return self.expected
        return "ask" if self.expected.ask else "grammar"


def patch(**fields):
    return edits.Edit(patch=tuple(fields.items()))


# Synthetic owner texts. Text goes straight to edits.read unless a remainder is
# specified. Prices in finance are explicit local fixtures, not parsed here.
PHRASES = (
    # Price and unit, including exact input vs. the upstream finance split.
    Phrase("make it 4 bucks", UNCLEAR),
    Phrase("$4.50 a pound", UNCLEAR),
    Phrase("each not per lb", MAPPER),
    Phrase("make it four bucks", MAPPER),
    Phrase("four dollars and fifty cents a pound", MAPPER),
    Phrase("sell it for five dollars each", MAPPER),
    Phrase("make it $4", ASK_PRICE),
    Phrase("price is 4.50 each", ASK_PRICE),
    Phrase("change the price to 4.50 a pound", patch(sellingPrice="4.50", priceUnit="lb"), price="4.50"),
    Phrase("now $4 each", patch(sellingPrice="4.00", priceUnit="each"), price="4.00"),
    Phrase("actually 4 or 5 bucks", UNCLEAR),
    Phrase("per pound please", MAPPER),
    Phrase("actually make it four bucks", patch(sellingPrice="4.00"), price="4.00", remainder="make it"),
    Phrase("okay make it 4 bucks", patch(sellingPrice="4.00"), price="4.00", remainder="okay make it"),
    Phrase("$4.50 per lb", patch(sellingPrice="4.50", priceUnit="lb"), price="4.50", sold_by="pound", remainder=""),
    Phrase("sell it for five bucks each", patch(sellingPrice="5.00", priceUnit="each"),
           price="5.00", sold_by="item", remainder="sell it for"),
    # Name.
    Phrase("call it Wildflower Honey", patch(name="Wildflower Honey")),
    Phrase("name: Lemon Tea", patch(name="Lemon Tea")),
    Phrase("name it Three Hills Wildflower Honey", patch(name="Three Hills Wildflower Honey"),
           explicit_value=("name", "Three Hills Wildflower Honey")),
    Phrase("call it Wildflower Honey please", patch(name="Wildflower Honey please")),
    Phrase('call it "Wildflower Honey"', MAPPER),
    Phrase("rename it to Orchard Honey", MAPPER),
    Phrase("call it Wildflower Honey!", MAPPER),
    Phrase("name it Orchard Blend No 7", patch(name="Orchard Blend No 7"),
           explicit_value=("name", "Orchard Blend No 7")),
    # Maker and source.
    Phrase("made by Miners", patch(maker="Miners")),
    Phrase("made by Lantern Kitchen, Pebble Bay", patch(maker="Lantern Kitchen", makerTown="Pebble Bay")),
    Phrase("made by little lantern jam kitchen", patch(maker="Little Lantern Jam Kitchen"),
           explicit_value=("maker", "little lantern jam kitchen")),
    Phrase("it's Miners' honey", MAPPER),
    Phrase("no maker", MAPPER),
    Phrase("leave the maker blank", MAPPER),
    Phrase("made by Miners or Lantern Kitchen", GENERIC_ASK),
    Phrase("from Etto", patch(supplier="Etto")),
    Phrase("from little lantern trading co", patch(supplier="Little Lantern Trading Co"),
           explicit_value=("supplier", "little lantern trading co")),
    Phrase("from Etto maybe", edits.Edit(ask="ask_edit_source", ask_args=(("name", "Etto maybe"),))),
    Phrase('Looks good otherwise. This is from "Etto".', patch(supplier="Etto")),
    Phrase("we get it from Lantern Kitchen", patch(supplier="Lantern Kitchen")),
    Phrase("swap the supplier to Lantern Kitchen", MAPPER),
    Phrase("take the source off", MAPPER),
    # Wording and owner copy.
    Phrase("shorter", REWRITE),
    Phrase("less fancy", REWRITE),
    Phrase("make it simpler", REWRITE),
    Phrase("bit warmer", REWRITE),
    Phrase("a little less fancy", REWRITE),
    Phrase("shorter please", MAPPER),
    Phrase("make the description a little shorter", MAPPER),
    Phrase("make it 2 lines shorter", UNCLEAR),
    Phrase("add: great on toast", GENERIC_ASK),
    Phrase("add: really good on warm toast", GENERIC_ASK),
    Phrase("add: nice with tea on a cold day", GENERIC_ASK),
    Phrase("say it's nice with tea on a cold day", MAPPER),
    # Category.
    Phrase("put it in pantry", patch(category="pantry")),
    Phrase("category: Bread", patch(category="bread")),
    Phrase("shelf: drinks", patch(category="drinks")),
    Phrase("move that to dairy", MAPPER),
    Phrase("put it under fruit please", MAPPER),
    Phrase("category: snacks", MAPPER),
    # Picture.
    Phrase("use my photo", PICTURE),
    Phrase("try the picture again", PICTURE),
    Phrase("different picture", PICTURE),
    Phrase("use my photo please", MAPPER),
    Phrase("use the photo I just sent", MAPPER),
    Phrase("use photo 2", UNCLEAR),
    # Nonsense/questions: a question stays local even without a question mark.
    Phrase("asdf hjkl", MAPPER),
    Phrase("what did you put for the maker", UNCLEAR),
    Phrase("Hass, is this on the site yet?", UNCLEAR),
)


def words(text):
    return re.findall(r"[^\W_]+", text.casefold())


def four_word_spans(tokens):
    return set(zip(tokens, tokens[1:], tokens[2:], tokens[3:]))


class EditPhraseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, files, _ = assets()
        cls.grammar = edits.Grammar(files)

    def test_c1_table(self):
        # C1: catch a form capturing the wrong value, or silent drift between
        # local handling and fallback. With no mapper both misses ask the same thing.
        self.assertGreaterEqual(len(PHRASES), 40)
        self.assertEqual(len({row.text for row in PHRASES}), len(PHRASES))
        for row in PHRASES:
            with self.subTest(text=row.text):
                expected = GENERIC_ASK if isinstance(row.expected, str) else row.expected
                self.assertEqual(row.read(self.grammar), expected)
                # Use a no-op callback to observe route eligibility, not to predict Sol's output.
                if not re.search(r"\d", row.text):  # C3 checks callback suppression for digit rows.
                    spy = Mock(return_value=None)
                    row.read(self.grammar, mapper=spy)
                    if row.expected == MAPPER:
                        spy.assert_called_once()
                    else:
                        spy.assert_not_called()
                if expected == GENERIC_ASK:
                    # A form that asks (e.g. add:) is not an unmatched local miss.
                    self.assertEqual(self.grammar.match(row.text) is not None, row.bucket == "ask")

    def test_c2_no_paste(self):
        # C2 / F1: catch an edit accidentally copying owner chatter into any
        # string patch field. Only an explicitly declared field/value is exempt.
        for row in PHRASES:
            owner_spans = four_word_spans(words(row.text))
            for field, value in row.read(self.grammar).patch:
                if not isinstance(value, str):
                    continue
                with self.subTest(text=row.text, field=field):
                    if row.explicit_value:
                        explicit_field, explicit_value = row.explicit_value
                        if field == explicit_field and " ".join(value.casefold().split()) == explicit_value.casefold():
                            continue
                    self.assertFalse(owner_spans & four_word_spans(words(value)), value)

    def test_c3_digits_stay_local(self):
        # C3: catch a new route sending an unmatched amount, photo index or
        # length to the mapper (which would still look like an ask with no mapper).
        digit_rows = [row for row in PHRASES if re.search(r"\d", row.text)]
        self.assertTrue(digit_rows)
        for row in digit_rows:
            with self.subTest(text=row.text):
                spy = Mock(return_value=None)
                row.read(self.grammar, mapper=spy)
                spy.assert_not_called()

    def test_c4_report_matches(self):
        # C4: catch stale totals or omitted/mislabelled fallback rows after a
        # fixture change, even when the behavioural expectations are up to date.
        report = (Path(__file__).resolve().parents[2] / "docs/hass/NPP-EDIT-PHRASES.md").read_text(encoding="utf-8")
        counts = re.findall(r"\b(grammar|ask|mapper|unclear): (\d+)\b", report)
        self.assertEqual(len(counts), 4)
        self.assertEqual({key: int(value) for key, value in counts}, Counter(row.bucket for row in PHRASES))
        report_rows = re.findall(r"^\| `([^`]+)` \| `(mapper|ask_edit_unclear)` \|$", report, re.M)
        self.assertCountEqual(report_rows, [(row.text, MAPPER if row.bucket == MAPPER else GENERIC_ASK.ask)
                                           for row in PHRASES if row.bucket in (MAPPER, UNCLEAR)])
