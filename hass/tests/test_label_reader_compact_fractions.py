"""A compact mixed-fraction weight is a size only when it fills the identity field."""

import unittest

from hass.label_reader import keep


class CompactFractionSizes(unittest.TestCase):
    def test_compact_mixed_fraction_sizes_are_not_identities(self):
        # Requiring a space before the fraction lets bare weights through.
        for field, value in (("name", "1½ oz"), ("brand", "2¾ lb")):
            with self.subTest(field=field, value=value):
                self.assertEqual(keep({field: value}, ()), {})

    def test_compact_size_with_name_text_is_kept(self):
        # Matching a size prefix instead of the whole field would drop this name.
        self.assertEqual(keep({"name": "1½ oz Coffee"}, ()), {"name": "1½ oz Coffee"})
