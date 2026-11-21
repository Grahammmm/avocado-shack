"""Canonical content envelopes require JSON integer 1, not just a value equal to 1."""

import tempfile
import unittest
from pathlib import Path

from hass.content_model import Content, ContentError, load_content


class ContentSchemaVersionTypeTests(unittest.TestCase):
    _PAYLOADS = {
        "products.json": ', "products": []',
        "makers.json": ', "makers": {}',
        "community.json": ', "fixture": "community"',
        "store.json": ', "fixture": "store"',
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in self._PAYLOADS:
            self._write(name, "1")

    def _write(self, name, version):
        # Write literal JSON so 1e0 is not normalized to 1.0 by serialization.
        (self.root / name).write_text(
            '{"schemaVersion": ' + version + self._PAYLOADS[name] + '}', encoding="utf-8"
        )

    def test_integer_one_preserves_loaded_content(self):
        self.assertEqual(
            load_content(self.root),
            Content([], {}, {"fixture": "community"}, {"schemaVersion": 1, "fixture": "store"}),
        )

    def test_other_versions_report_the_affected_file(self):
        # Equality alone wrongly accepts True and 1.0 after JSON decoding.
        for name in self._PAYLOADS:
            for version in ("true", "1.0", "1e0", '"1"', "null", "2"):
                with self.subTest(file=name, version=version):
                    self._write(name, version)
                    try:
                        with self.assertRaises(ContentError) as ctx:
                            load_content(self.root)
                        self.assertEqual(ctx.exception.problems, [f"{name}: schemaVersion must be 1"])
                    finally:
                        self._write(name, "1")
