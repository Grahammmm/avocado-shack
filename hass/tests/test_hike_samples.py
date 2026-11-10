"""AV1422-10 (H04) tests: ``hike.samples {show}`` hides or shows the labelled sample hikes with one club flag.

Ops run through the H02 editor on a throwaway repo (test_hike_ops.HikeRepo). The browser test skips without
PLAYWRIGHT_MODULE. Run: python3 -B -m unittest hass.tests.test_hike_samples -v
"""

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from hass import sitegen
from hass.content_model import load_and_validate
from hass.tests.test_hike_ops import HikeTestCase

REPO = Path(__file__).resolve().parents[2]
OP = "hike.samples"
BROWSER_JS = """
const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
(async()=>{const b=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const p=await b.newPage(),trail=[];p.on('request',r=>{if(/point-buchon/.test(r.url()))trail.push(r.url())});
 await p.goto(process.env.URL+'/hike',{waitUntil:'networkidle'});
 await p.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));await p.waitForTimeout(800);
 const text=await p.evaluate(()=>document.body.innerText);
 console.log(JSON.stringify({invitation:await p.locator('.trail-invitation #featured-hike-title').count(),archive:/Sample archive/.test(text),
   trail:trail.length,real:await p.locator('.hike-event h2',{hasText:'Real test hike'}).count()}));await b.close()})();
"""


class SamplesTests(HikeTestCase):
    def club(self, repo, site=False):
        path = repo.wt / ("storefront-mockup/community.json" if site else "hass/content/community.json")
        data = json.loads(path.read_text("utf-8"))
        return data["club"] if not site else data

    def test_hide_writes_flag_everywhere_and_show_removes_it(self):
        repo = self.repo()
        repo.run((OP, {"show": False}))
        self.assertIs(self.club(repo)["showSamples"], False)
        self.assertIs(self.club(repo, site=True)["showSamples"], False)
        content = load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")
        self.assertIs(json.loads(sitegen._public_community_json(content))["showSamples"], False)
        repo.run((OP, {"show": True}))
        self.assertNotIn("showSamples", self.club(repo))
        self.assertNotIn("showSamples", self.club(repo, site=True))
        content = load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")
        self.assertNotIn("showSamples", json.loads(sitegen._public_community_json(content)))

    def test_repeat_is_refused_and_writes_nothing(self):
        repo = self.repo()
        self.assertEqual(self.assertRejected(repo, "refused", (OP, {"show": True}))["reason"],
                         "the sample hikes are already shown")
        repo.run((OP, {"show": False}))
        self.assertEqual(self.assertRejected(repo, "refused", (OP, {"show": False}))["reason"],
                         "the sample hikes are already hidden")

    def test_undo_restores_the_previous_state_both_ways(self):
        repo = self.repo()
        base = self.club(repo)
        hid = repo.run((OP, {"show": False}))
        repo.run(("history.revert", {"changeId": hid["change_id"]}))
        self.assertEqual(self.club(repo), base)
        repo.run((OP, {"show": False}))
        shown = repo.run((OP, {"show": True}))
        repo.run(("history.revert", {"changeId": shown["change_id"]}))
        self.assertIs(self.club(repo)["showSamples"], False)

    def test_text_for_show_is_invalid_and_writes_nothing(self):
        repo = self.repo()
        self.assertRejected(repo, "invalid", (OP, {"show": "no"}))
        self.assertNotIn("showSamples", self.club(repo))

    def test_hand_edited_non_bool_is_a_content_error_naming_the_field(self):
        repo = self.repo()
        for bad in ("no", 1, None):
            with self.subTest(bad=bad):
                path = repo.wt / "hass/content/community.json"
                data = json.loads(path.read_text("utf-8"))
                data["club"]["showSamples"] = bad
                path.write_text(json.dumps(data), "utf-8")
                with self.assertRaises(Exception) as caught:
                    load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")
                self.assertIn("community.club.showSamples: must be true or false", str(caught.exception))

    def test_prompt_names_hidden_samples_only_when_hidden(self):
        from hass.interpreter_prompt import build as build_prompt
        from hass.ops import load_registry
        content = load_and_validate(REPO / "hass/content", REPO / "storefront-mockup")
        self.assertNotIn("samples | hidden", build_prompt(load_registry(), content))
        content.community["club"]["showSamples"] = False
        self.assertIn("\nsamples | hidden", build_prompt(load_registry(), content))

    def test_absent_flag_leaves_public_json_keys_unchanged(self):
        content = load_and_validate(REPO / "hass/content", REPO / "storefront-mockup")
        self.assertNotIn("showSamples", content.community["club"])
        self.assertNotIn("showSamples", json.loads(sitegen._public_community_json(content)))
        self.assertNotIn("showSamples", json.loads(sitegen._community_json(content)))


class LiveServerTests(unittest.TestCase):
    def serve(self, config):
        tmp = tempfile.TemporaryDirectory(prefix="hass-samples-")
        self.addCleanup(tmp.cleanup)
        cfg = Path(tmp.name) / "community.json"
        cfg.write_text(json.dumps(config), "utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "AVOSHACK_COMMUNITY_DB": str(Path(tmp.name) / "c.sqlite3"), "AVOSHACK_COMMUNITY_CONFIG": str(cfg)}
        server = subprocess.Popen([sys.executable, str(REPO / "storefront-mockup/community-server.py"), "--port", str(port)],
                                  env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.terminate)
        return port

    def api(self, port):
        for _ in range(100):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/api/community")
                return json.loads(conn.getresponse().read())
            except ConnectionRefusedError:
                time.sleep(0.1)
        self.fail("community server did not start")

    def base(self):
        return json.loads((REPO / "storefront-mockup/community.json").read_text("utf-8"))

    def test_api_carries_flag_only_when_hidden(self):
        self.assertIs(self.api(self.serve({**self.base(), "showSamples": False}))["showSamples"], False)
        self.assertNotIn("showSamples", self.api(self.serve(self.base())))
        self.assertNotIn("showSamples", self.api(self.serve({**self.base(), "showSamples": True})))

    @unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
    def test_hike_page_hides_samples_but_keeps_a_real_hike(self):
        real = {"id": "hike-2099-12-05-real", "title": "Real test hike", "status": "scheduled",
                "startsAt": "2099-12-05T09:00:00-08:00", "timezone": "America/Los_Angeles", "description": "A real one.",
                "meetingPoint": "Test lot", "rsvpEnabled": False}
        script = Path(tempfile.mkdtemp(prefix="hass-samples-js-")) / "check.cjs"
        script.write_text(BROWSER_JS, "utf-8")

        def look(config):
            port = self.serve(config)
            self.api(port)
            out = subprocess.run(["node", str(script)], env={**os.environ, "URL": f"http://127.0.0.1:{port}"},
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(out.returncode, 0, out.stderr)
            return json.loads(out.stdout)

        shown = look(self.base())
        self.assertGreater(shown["invitation"], 0)  # control: samples show today
        self.assertTrue(shown["archive"])
        hidden = look({**self.base(), "showSamples": False})
        self.assertEqual((hidden["invitation"], hidden["archive"], hidden["trail"]), (0, False, 0))
        both = look({**self.base(), "showSamples": False, "events": [real]})
        self.assertEqual((both["invitation"], both["archive"], both["real"]), (0, False, 1))


if __name__ == "__main__":
    unittest.main()
