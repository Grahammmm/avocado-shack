"""RF1501-9: a cached category value that is valid JSON but not a list reads as an unreadable cache, (None, False).
Synthetic rows and fake ids only; no token, no network.
Run: python3 -B -m unittest hass.tests.test_clover_cache_category_shapes
"""
import os
import shutil
import socket
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass.clover import cache
from hass.tests.test_clover_cache import PROD_A, PROD_B, fixture_rows
from hass.tests.test_clover_cli import T0


class CategoryShapeTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="clover-cats-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        os.chmod(self.state, 0o700)
        patcher = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network"))
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)

    def set_cats(self, text, where=""):
        db = sqlite3.connect(cache.path_for(self.state))
        with db:
            db.execute(f"UPDATE items SET categories = ? {where}", (text,))
        db.close()

    def db_bytes(self):
        return cache.path_for(self.state).read_bytes()

    def test_noniterable_category_json_is_unreadable(self):
        for text in ("null", "5", "1.5", "true", "false"):
            with self.subTest(text=text):
                self.set_cats(text)
                before = self.db_bytes()
                self.assertEqual(cache.read(self.state, PROD_A), (None, False))
                self.assertEqual(self.db_bytes(), before)

    def test_one_bad_category_row_invalidates_whole_snapshot(self):
        self.set_cats("null", "WHERE id = (SELECT max(id) FROM items)")
        self.assertEqual(cache.read(self.state, PROD_A), (None, False))

    def test_valid_category_lists_round_trip(self):
        self.set_cats('["Früchte", "Obst"]')
        snapshot, reachable = cache.read(self.state, PROD_A)
        self.assertEqual((snapshot.items[0].categories, snapshot.fetched_at, reachable), (("Früchte", "Obst"), T0, True))
        self.set_cats("[]")
        self.assertEqual(cache.read(self.state, PROD_A)[0].items[0].categories, ())
        cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=15), identity=PROD_A)
        snapshot, reachable = cache.read(self.state, PROD_A)
        self.assertEqual((len(snapshot.items), reachable), (6, False))

    def test_identity_refusal_precedes_category_decode(self):
        self.set_cats("null")
        before = self.db_bytes()
        self.assertEqual(cache.read(self.state, PROD_B), (None, True))
        self.assertEqual(self.db_bytes(), before)

    def test_invalid_json_keeps_existing_unreadable_result(self):
        self.set_cats("[oops")
        self.assertEqual(cache.read(self.state, PROD_A), (None, False))
        empty = Path(tempfile.mkdtemp(prefix="clover-cats-"))
        self.addCleanup(shutil.rmtree, empty, True)
        os.chmod(empty, 0o700)
        self.assertEqual(cache.read(empty, PROD_A), (None, True))
        self.assertFalse(cache.path_for(empty).exists())


if __name__ == "__main__":
    unittest.main()
