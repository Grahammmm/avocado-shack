"""HASS-CLOVER-2: host.json's optional `clover` block in hass/host.py (load_host, check, make_worker wiring) and hass/health.py.
The token file is judged by stat only: a missing, unreadable, wrong-mode or wrong-owner file is one plain word, never the path or a byte.
Run: python3 -B -m unittest hass.tests.test_clover_host
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import health, host
from hass.clover import cache, chat
from hass.tests.test_clover_chat import seed
from hass.tests.test_clover_cli import T0
from hass.tests.test_clover_client import FAKE_TOKEN
from hass.tests.test_editor import git
from hass.tests.test_host import HostCase

MID = "FAKEMERCH0001"


class SecretCase(HostCase):
    def setUp(self):
        super().setUp()
        self.secret_dir = Path(tempfile.mkdtemp(prefix="clover-secret-"))
        self.addCleanup(shutil.rmtree, self.secret_dir, True)
        os.chmod(self.secret_dir, 0o700)
        self.token = self.write(self.secret_dir / "production-read.token", FAKE_TOKEN.encode())

    def block(self, **over):
        return {"environment": "production", "merchantId": MID, "tokenFile": str(self.token), "liveApproved": False, **over}


class CloverHostTests(SecretCase):
    def test_the_block_is_optional_and_validated_by_field_name(self):
        self.assertNotIn("clover", host.load_host(self.host_json()))
        self.assertEqual(host.load_host(self.host_json(clover=self.block()))["clover"]["merchantId"], MID)
        for bad, fields in ((self.block(environment="live"), ["clover.environment"]), (self.block(extra=1), ["clover.extra"]),
                            ({"environment": "production"}, ["clover.merchantId", "clover.tokenFile"]), ("x", ["clover"]),
                            (self.block(liveApproved="yes"), ["clover.liveApproved"]), (self.block(tokenFile="token.txt"), ["clover.tokenFile"])):
            with self.subTest(fields=fields), self.assertRaises(host.HostConfigError) as ctx:
                host.load_host(self.host_json(clover=bad))
            self.assertEqual(ctx.exception.fields, fields)
            self.assertNotIn(str(self.secret_dir), str(ctx.exception))

    def test_clover_state_is_one_word_from_stat_only(self):
        cfg = host.load_host(self.host_json(clover=self.block()))
        with mock.patch("os.open", side_effect=AssertionError("opened")), mock.patch("builtins.open", side_effect=AssertionError("opened")):
            self.assertEqual(host.clover_state(cfg), "ok")
            self.assertEqual(host.clover_state({"state": "/nowhere"}), "not configured")
        os.chmod(self.token, 0o644)
        self.assertEqual(host.clover_state(cfg), "mode")
        os.chmod(self.token, 0o600)
        os.chmod(self.secret_dir, 0o770)
        self.assertEqual(host.clover_state(cfg), "folder")
        os.chmod(self.secret_dir, 0o700)
        os.unlink(self.token)
        self.assertEqual(host.clover_state(cfg), "missing")

    def test_check_reports_the_clover_state(self):
        ck = Path(tempfile.mkdtemp(prefix="hass-ck-"))
        self.addCleanup(lambda: shutil.rmtree(ck, ignore_errors=True))
        for args in (("init", "-q"), ("config", "user.name", "t"), ("config", "user.email", "t@example.invalid")):
            git(ck, *args)
        (ck / "f").write_text("x")
        git(ck, "add", "f")
        git(ck, "commit", "-q", "-m", "c")
        head = git(ck, "rev-parse", "HEAD")

        def run(**over):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = host.main(["check", "--host", str(self.host_json(runtimeCommit=head, **over))], root=ck)
            self.assertNotIn(str(self.secret_dir), out.getvalue())
            self.assertNotIn(FAKE_TOKEN, out.getvalue())
            return code, json.loads(out.getvalue())
        self.assertEqual(run(), (0, {"result": "ok", "clover": "not configured"}))
        self.assertEqual(run(clover=self.block()), (0, {"result": "ok", "clover": "ok"}))
        os.chmod(self.token, 0o640)
        self.assertEqual(run(clover=self.block()), (2, {"result": "clover", "clover": "mode"}))
        os.unlink(self.token)
        self.assertEqual(run(clover=self.block()), (2, {"result": "clover", "clover": "missing"}))
        self.assertEqual(run(clover=self.block(merchantId="x")), (2, {"result": "config", "fields": ["clover.merchantId"]}))

    def test_make_worker_attaches_the_till_desk_only_with_a_block(self):
        built = []

        class FakeConv:
            def __init__(self, *a, **k):
                self.settings, self.editor = {}, None
                built.append(self)
        with mock.patch.object(host, "_worktree", return_value="/nowhere"), mock.patch.object(host.conversation, "Conversation", FakeConv), \
                mock.patch.object(host.receiver, "Receiver"), mock.patch.object(host.inbox_mod, "Inbox"), \
                mock.patch.object(host, "Worker"):
            host.make_worker(host.load_host(self.host_json()), None, build=lambda: None)
            host.make_worker(host.load_host(self.host_json(clover=self.block())), None, build=lambda: None)
        self.assertFalse(hasattr(built[0], "till"))
        self.assertIsInstance(built[1].till, chat.TillDesk)
        self.assertEqual(repr(built[1].till), "TillDesk(read-only)")


class CloverHealthTests(SecretCase):
    def problems(self, cfg, now=T0):
        out = []
        health._clover_checks(cfg, now, out)
        return out

    def cfg(self):
        state = Path(tempfile.mkdtemp(prefix="clover-health-"))
        self.addCleanup(shutil.rmtree, state, True)
        os.chmod(state, 0o700)
        return {"state": str(state), "clover": self.block()}

    def test_token_problems_are_one_word_and_the_token_is_never_opened(self):
        cfg = self.cfg()
        with mock.patch("os.open", side_effect=AssertionError("opened")):
            self.assertEqual(self.problems(cfg), [])
        os.chmod(self.token, 0o644)
        self.assertEqual(self.problems(cfg), [{"check": "clover-token", "detail": "mode"}])
        os.unlink(self.token)
        found = self.problems(cfg)
        self.assertEqual(found, [{"check": "clover-token", "detail": "missing"}])
        self.assertNotIn(str(self.secret_dir), json.dumps(found))

    def test_sync_age_and_failures(self):
        cfg = self.cfg()
        self.assertEqual(self.problems(cfg), [])                                      # no cache yet: the timer may not have run
        seed(cfg["state"], T0)
        self.assertEqual(self.problems(cfg, T0 + timedelta(minutes=90)), [])
        cache.record_failure(cfg["state"], "refused-key", T0 + timedelta(minutes=100))
        self.assertEqual(self.problems(cfg, T0 + timedelta(hours=3)),
                         [{"check": "clover-sync", "detail": "no good pull for over 2 h (last: refused-key)"}])
        os.chmod(cache.path_for(cfg["state"]), 0o644)
        self.assertEqual(self.problems(cfg), [{"check": "clover-sync", "detail": "cache not private or unreadable"}])

    def test_health_with_a_host_dir_runs_the_clover_checks(self):
        os.chmod(self.token, 0o644)
        self.host_json(clover=self.block())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            health.main(["--state", str(self.repo.state), "--host-dir", str(self.hostdir)], now=T0)
        doc = json.loads(out.getvalue())
        self.assertIn({"check": "clover-token", "detail": "mode"}, [{k: p[k] for k in ("check", "detail")} for p in doc["problems"]])
        self.assertNotIn(str(self.secret_dir), out.getvalue())
