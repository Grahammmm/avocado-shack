"""Migration checks distinguish baseline makers from newly added makers."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hass.content_model import REPO_ROOT, load_and_validate
from hass.migration_check import run_checks
from hass.sitegen import render, write_files


class MigrationMakerUrlTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-migration-maker-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.content = self.root / "hass/content"
        self.site = self.root / "storefront-mockup"
        for rel in ("hass/content", "hass/templates", "storefront-mockup"):
            shutil.copytree(REPO_ROOT / rel, self.root / rel, symlinks=True)
        self.makers_path = self.content / "makers.json"
        self.document = json.loads(self.makers_path.read_text("utf-8"))
        self.makers = self.document["makers"]
        self.makers["Fixture Farm"] = {"name": "Fixture Farm", "place": "California"}

    def migration_failures(self):
        self.makers_path.write_text(json.dumps(self.document), encoding="utf-8")
        content = load_and_validate(self.content, self.site)
        write_files(render(content, self.root / "hass/templates"), self.root)
        return run_checks(self.root)[0]

    def test_moving_url_to_new_maker_names_baseline_maker(self):
        # The old URL is still recorded globally, but is no longer Etto's source link.
        self.makers["Fixture Farm"]["url"] = self.makers["Etto"].pop("url")
        self.assertEqual(self.migration_failures(), ["baseline makers missing an https source link: ['Etto']"])

    def test_new_maker_may_omit_url(self):
        # Requiring a link on every maker rather than just baseline makers would fail this check.
        self.assertEqual(self.migration_failures(), [])
