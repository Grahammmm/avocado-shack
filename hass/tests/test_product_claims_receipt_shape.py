"""A decoded sidecar must have the expected shape before it can support a claim."""
import json
from pathlib import Path
import tempfile
import unittest

from hass import product_claims


class ReceiptShapeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.sha = 'a' * 64
        self.claim = ['Fruit Jam']
        self.receipt = {'source': 'label', 'photo': self.sha, 'text': self.claim}
        self.path = self.root / 'labels' / (self.sha + '.json')
        self.path.parent.mkdir(mode=0o700)

    def resolve(self, receipt):
        self.path.write_text(json.dumps(receipt), encoding='utf-8')
        return product_claims.source(self.root, self.sha, self.claim)

    def test_non_object_receipt_is_missing(self):
        # Decoding succeeds, but non-objects cannot be queried for receipt fields.
        for receipt in (None, [], 'Fruit Jam'):
            with self.subTest(shape=type(receipt).__name__):
                self.assertIsNone(self.resolve(receipt))

    def test_wrong_shaped_text_is_missing(self):
        # Matching identity and membership alone do not validate the text field.
        for lines in (None, 'Fruit Jam', {'Fruit Jam': True}, ['Fruit Jam', 1]):
            with self.subTest(shape=type(lines).__name__):
                self.assertIsNone(self.resolve({**self.receipt, 'text': lines}))
        self.assertIsNone(self.resolve({'source': 'label', 'photo': self.sha}))

    def test_valid_receipt_returns_requested_label_line(self):
        self.assertEqual(self.resolve({**self.receipt, 'text': ['Fruit Jam', 'Extra line']}),
                         self.receipt)
