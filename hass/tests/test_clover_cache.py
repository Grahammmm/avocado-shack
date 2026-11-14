"""HASS-CLOVER-1-FIX-2: the private till cache knows which till it holds (environment + merchantId + schema in its meta table).

A snapshot is read, and its backoff trusted, only for the configured till. A cache written for another environment or merchant, or an
older cache with no identity, is refused with the reason word `identity` until a good pull of the configured till replaces it.
Fixtures and fake merchant ids only; no token, no network.
Run: python3 -B -m unittest hass.tests.test_clover_cache
"""
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from hass import health
from hass.clover import cache, sync
from hass.tests.test_clover_cli import T0
from hass.tests.test_clover_client import fixture

PROD_A = cache.Identity("production", "FAKEMERCH0001")
PROD_B = cache.Identity("production", "FAKEMERCH0002")
SANDBOX_A = cache.Identity("sandbox", "FAKEMERCH0001")


def fixture_rows():
    return sync.rows(fixture("items.json")["elements"], fixture("item_stocks.json")["elements"])[0]


class CacheCase(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="clover-cache-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        os.chmod(self.state, 0o700)

    def meta(self):
        db = sqlite3.connect(cache.path_for(self.state))
        self.addCleanup(db.close)
        return dict(db.execute("SELECT key, value FROM meta"))

    def item_count(self):
        db = sqlite3.connect(cache.path_for(self.state))
        self.addCleanup(db.close)
        return db.execute("SELECT count(*) FROM items").fetchone()[0]

    def strip_identity(self):
        """An older cache: the same items and freshness rows, but no environment, merchantId or schema."""
        db = sqlite3.connect(cache.path_for(self.state))
        with db:
            db.execute("DELETE FROM meta WHERE key IN ('environment', 'merchantId', 'schema')")
        db.close()


class IdentityTests(CacheCase):
    def test_a_good_pull_records_its_till_in_the_same_transaction(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        meta = self.meta()
        self.assertEqual((meta["environment"], meta["merchantId"], meta["schema"]), ("production", "FAKEMERCH0001", cache.SCHEMA_VERSION))
        snapshot, reachable = cache.read(self.state, PROD_A)
        self.assertEqual((len(snapshot.items), reachable), (6, True))
        facts = cache.facts(self.state, PROD_A)
        self.assertEqual((facts["environment"], facts["merchantId"], facts["itemCount"]), ("production", "FAKEMERCH0001", 6))
        self.assertNotIn("refused", facts)

    def test_a_failed_write_leaves_neither_rows_nor_identity(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        bad = fixture_rows()
        del bad[-1]["name"]
        with self.assertRaises(KeyError):
            cache.write_items(self.state, bad, T0 + timedelta(minutes=15), PROD_B)
        self.assertEqual((self.meta()["merchantId"], self.item_count()), ("FAKEMERCH0001", 6))   # the rollback kept A whole

    def test_merchant_a_to_b_is_refused_until_b_syncs(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        self.assertEqual(cache.read(self.state, PROD_B), (None, True))      # nothing tried for B yet: "haven't been able to read the till"
        self.assertEqual(cache.facts(self.state, PROD_B), {"refused": "identity", "environment": "production", "merchantId": "FAKEMERCH0001"})
        cache.write_items(self.state, fixture_rows()[:2], T0 + timedelta(minutes=15), PROD_B)
        self.assertEqual(len(cache.read(self.state, PROD_B)[0].items), 2)
        self.assertEqual(cache.read(self.state, PROD_A), (None, True))      # and A's identity is now the stranger

    def test_sandbox_to_production_is_refused(self):
        cache.write_items(self.state, fixture_rows(), T0, SANDBOX_A)
        self.assertEqual(cache.read(self.state, PROD_A), (None, True))
        self.assertEqual(cache.facts(self.state, PROD_A)["refused"], "identity")
        self.assertEqual(len(cache.read(self.state, SANDBOX_A)[0].items), 6)

    def test_a_legacy_cache_without_identity_is_refused(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        self.strip_identity()
        self.assertEqual(cache.read(self.state, PROD_A), (None, True))
        self.assertEqual(cache.facts(self.state, PROD_A), {"refused": "identity", "environment": None, "merchantId": None})
        db = sqlite3.connect(cache.path_for(self.state))         # a wrong schema word is refused as well
        with db:
            db.execute("INSERT INTO meta(key, value) VALUES ('environment', 'production'), ('merchantId', 'FAKEMERCH0001'), "
                       "('schema', 'clover-cache-0')")
        db.close()
        self.assertEqual(cache.read(self.state, PROD_A), (None, True))

    def test_an_incomplete_configured_identity_never_matches(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        for ident in (cache.Identity("production", None), cache.Identity(None, "FAKEMERCH0001"), cache.Identity("", ""), None):
            with self.subTest(ident=ident):
                self.assertEqual(cache.read(self.state, ident), (None, True))
                self.assertEqual(cache.facts(self.state, ident)["refused"], "identity")
        with self.assertRaises(ValueError):
            cache.write_items(self.state, fixture_rows(), T0, cache.Identity("production", None))

    def test_backoff_is_kept_for_the_same_till_and_never_inherited(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        self.assertEqual(cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=15), identity=PROD_A), 1)
        self.assertEqual(cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=30), identity=PROD_A), 2)
        self.assertEqual(cache.facts(self.state, PROD_A)["nextAttempt"], "2026-11-10T21:00:00+00:00")
        self.assertEqual(self.item_count(), 6)                                   # the same till's last good pull is kept
        self.assertNotIn("nextAttempt", cache.facts(self.state, PROD_B))        # B sees no backoff to obey
        # B's first failure starts B's own record: count 1, A's rows gone, and nothing to quote for B
        self.assertEqual(cache.record_failure(self.state, "refused-key", T0 + timedelta(minutes=35), identity=PROD_B), 1)
        facts = cache.facts(self.state, PROD_B)
        self.assertEqual((facts["merchantId"], facts["failures"], facts["asOf"], facts["itemCount"], facts["lastResult"]),
                         ("FAKEMERCH0002", 1, None, 0, "refused-key"))
        self.assertEqual(self.item_count(), 0)
        self.assertEqual(cache.read(self.state, PROD_B), (None, False))          # "I can't reach the till right now"
        self.assertEqual(cache.facts(self.state, PROD_A)["refused"], "identity")

    def test_a_legacy_backoff_is_not_inherited(self):
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=15), identity=PROD_A)
        self.strip_identity()
        self.assertNotIn("nextAttempt", cache.facts(self.state, PROD_A))
        self.assertEqual(cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=20), identity=PROD_A), 1)
        self.assertEqual(self.item_count(), 0)                                   # unidentified rows are never quoted again


class HealthIdentityTests(CacheCase):
    def problems(self, block, now=T0):
        out = []
        health._clover_checks({"state": str(self.state), "clover": {**block, "tokenFile": "/nowhere/x.token"}}, now, out)
        return [p for p in out if p["check"] == "clover-sync"]

    def test_clover_sync_reports_identity_by_word(self):
        a = {"environment": "production", "merchantId": "FAKEMERCH0001"}
        cache.write_items(self.state, fixture_rows(), T0, PROD_A)
        self.assertEqual(self.problems(a), [])
        found = self.problems({**a, "merchantId": "FAKEMERCH0002"})
        self.assertEqual(found, [{"check": "clover-sync", "detail": "identity: the cache is not for the configured till"}])
        self.assertEqual(self.problems({**a, "environment": "sandbox"}), found)
        self.strip_identity()
        self.assertEqual(self.problems(a), found)


if __name__ == "__main__":
    unittest.main()
