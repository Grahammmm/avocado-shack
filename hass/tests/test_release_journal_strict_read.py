"""Exercise release-book JSON parsing through private fixture files."""
import tempfile
import unittest
from pathlib import Path

from hass import release_journal as r


class StrictReadTests(unittest.TestCase):
    def setUp(self):
        fixture = self.enterContext(tempfile.NamedTemporaryFile(prefix='release-book-fixture-'))
        self.path = Path(fixture.name)

    def assert_refused(self, raw):
        self.path.write_bytes(raw)
        with self.assertRaises(r.BooksError) as ctx:
            r.read(self.path)
        self.assertEqual(str(ctx.exception), 'release-books; run adopt if missing')
        self.assertEqual(self.path.read_bytes(), raw)

    def test_rejects_nonstandard_constants_in_object_values_and_nested_arrays(self):
        # The default decoder silently accepts all three tokens, even inside summary.
        for token in (b'NaN', b'Infinity', b'-Infinity'):
            for shape in (b'{"summary":%s}', b'{"summary":{"samples":[%s]}}'):
                with self.subTest(token=token, shape=shape):
                    self.assert_refused(shape % token)

    def test_reads_finite_nested_json_and_quoted_constant_names(self):
        # A text scan instead of a decoder hook could also reject quoted strings.
        self.path.write_bytes(b'{"summary":{"samples":[0,-1.25,2e3,"NaN","Infinity","-Infinity"]}}')
        self.assertEqual(r.read(self.path), {'summary': {'samples': [0, -1.25, 2000.0, 'NaN', 'Infinity', '-Infinity']}})

    def test_rejects_nested_duplicate_keys(self):
        # Adding the constant hook must not replace the duplicate-key hook.
        self.assert_refused(b'{"summary":{"samples":1,"samples":2}}')
