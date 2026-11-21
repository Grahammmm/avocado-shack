"""Fixture coverage for duplicate JSON keys at the item-standard report boundary."""
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from hass import itemstd


PRODUCTS = b'{"schemaVersion": 1, "products": [{"id": "p", "name": "Peas", "status": "active"}]}\n'
MAKERS = b'{"schemaVersion": 1, "makers": {"Farm": {"name": "Farm"}}}\n'


class DuplicateKeysTest(unittest.TestCase):
    def setUp(self):
        self.content = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.content / "products.json").write_bytes(PRODUCTS)
        (self.content / "makers.json").write_bytes(MAKERS)

    def test_rejects_duplicate_object_keys(self):
        cases = (
            # Last-wins would silently change an active product to hidden.
            ("product status", "products.json", PRODUCTS.replace(
                b'"status": "active"', b'"status": "active", "status": "hidden"')),
            # A maker map must not silently replace the first record.
            ("maker key", "makers.json", MAKERS.replace(
                b'"Farm": {"name": "Farm"}', b'"Farm": {"name": "Farm"}, "Farm": {}')),
            # Even identical values must not make a repeated envelope key valid.
            ("schema envelope", "products.json", PRODUCTS.replace(
                b'"schemaVersion": 1', b'"schemaVersion": 1, "schemaVersion": 1')),
            # The parser must check decoded keys, even in metadata the report ignores.
            ("nested metadata", "makers.json", MAKERS.replace(
                b'"name": "Farm"', rb'"name": "Farm", "extra": [{"x": 0, "\u0078": 1}]')),
        )
        for label, filename, raw in cases:
            with self.subTest(case=label):
                (self.content / "products.json").write_bytes(raw if filename == "products.json" else PRODUCTS)
                (self.content / "makers.json").write_bytes(raw if filename == "makers.json" else MAKERS)
                with self.assertRaisesRegex(itemstd.ReportError, rf"{re.escape(filename)}:.*duplicate JSON object key"):
                    itemstd.report_for(self.content)

    def test_valid_report_preserves_records_and_exact_byte_hashes(self):
        # The two records both have a `name` key: uniqueness is per object, not per report.
        source = {
            "content": "a folder outside this repository",
            "products_sha256": hashlib.sha256(PRODUCTS).hexdigest(),
            "makers_sha256": hashlib.sha256(MAKERS).hexdigest(),
        }
        expected = itemstd.build_report(
            [{"id": "p", "name": "Peas", "status": "active"}], {"Farm": {"name": "Farm"}}, source,
        )
        self.assertEqual(itemstd.report_for(self.content), expected)
