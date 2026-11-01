"""NB-AV-06 (H19): health --model reports an unreachable or incomplete local model; change-only notify as before.

Fake transports and one loopback test server; temp 0700 state dirs and an injected clock. Never the real model or state.
"""
import contextlib, hashlib, http.server, io, json, os, shutil, tempfile, threading, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import health

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
URL, MARK = "http://127.0.0.1:11434", "SECRET-REPLY-TEXT"
TAGS = json.dumps({"models": [{"name": "qwen:latest"}, {"name": "llama3:8b"}, "junk"], "note": MARK}).encode()


def reply(status, body: object = b""):
    return lambda url, timeout: (status, body)


def fail(exc):
    def transport(url, timeout):
        raise exc
    return transport


class Server(http.server.BaseHTTPRequestHandler):
    hits, plan = [], (200, {}, TAGS)

    def do_GET(self):
        Server.hits.append(self.path)
        status, headers, body = Server.plan
        self.send_response(status)
        for key, value in headers.items(): self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - base signature
        pass


class HealthModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))
        self.calls = []

    def run_health(self, *extra, transport=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), *extra], now=NOW, transport=transport)
        [line] = out.getvalue().splitlines()
        for leak in ("127.0.0.1", "11434", "localhost", MARK, "api/tags"): self.assertNotIn(leak, line)
        return code, json.loads(line), line

    def recording(self, transport):
        def wrapped(url, timeout):
            self.calls.append((url, timeout))
            return transport(url, timeout)
        return wrapped

    def model_problems(self, transport, *extra):
        code, doc, _ = self.run_health("--model", URL, *extra, transport=self.recording(transport))
        self.assertEqual(code, 1 if doc["problems"] else 0)
        return [p["detail"] for p in doc["problems"] if p["check"] == "model"]

    def test_no_model_flag_output_unchanged(self):
        code, _, line = self.run_health(transport=fail(AssertionError("no call")))
        expected = {"fingerprint": hashlib.sha256(b"").hexdigest(), "info": [{"check": "conversation",
                    "detail": "no conversation yet"}], "notify": False, "ok": True, "problems": []}
        self.assertEqual((code, line), (0, json.dumps(expected, sort_keys=True)))
        self.assertNotIn("model", line)

    def test_listed_model_is_ok_and_name_without_tag_means_latest(self):
        for extra in ((), ("--model-name", "qwen"), ("--model-name", "qwen:latest"), ("--model-name", "llama3:8b")):
            self.assertEqual(self.model_problems(reply(200, TAGS), *extra), [], extra)
        self.assertEqual(self.calls[0], (URL + "/api/tags", 3))

    def test_missing_model_is_one_problem(self):
        for name in ("x:7b", "llama3", "qwen:7b", "QWEN"):
            self.assertEqual(self.model_problems(reply(200, TAGS), "--model-name", name), ["model not installed"], name)

    def test_each_failure_is_one_fixed_problem(self):
        cases = [(fail(ConnectionRefusedError()), "unreachable"), (fail(TimeoutError()), "unreachable"),
                 (fail(OSError("reset")), "unreachable"), (reply(503, MARK.encode()), "http 503"),
                 (reply(302), "http 302"), (reply(200, b"not json"), "bad reply"),
                 (reply(200, b'{"models": "x"}'), "bad reply"), (reply(200, b"[1]"), "bad reply"),
                 (reply(200, b"{}"), "bad reply"), (reply(200, b'{"models": []}' + b" " * 300 * 1024), "bad reply"),
                 (reply("200", TAGS), "bad reply"), (reply(200, None), "bad reply")]
        for transport, detail in cases:
            self.assertEqual(self.model_problems(transport, "--model-name", "qwen"), [detail], detail)

    def test_change_only_notify(self):
        seen, down, up = str(self.tmp / "seen"), fail(ConnectionRefusedError()), reply(200, TAGS)
        runs = [(down, True), (down, False), (up, True), (up, False), (reply(503), True)]
        for transport, notify in runs:
            code, doc, _ = self.run_health("--model", URL, "--seen", seen, transport=transport)
            self.assertEqual((code, doc["notify"]), (1 if doc["problems"] else 0, notify))

    def test_bad_flags_are_usage_errors_and_read_nothing(self):
        for extra in (["--model", "https://127.0.0.1"], ["--model", "http://192.168.1.2:11434"],
                      ["--model", "http://u:p@127.0.0.1:11434"], ["--model", URL + "/api"], ["--model", ""],
                      ["--model-name", "qwen"], ["--model", URL, "--model-name", ""]):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                health.main(["--state", str(self.state), *extra], now=NOW, transport=self.recording(reply(200, TAGS)))
            self.assertEqual((cm.exception.code, out.getvalue(), self.calls), (2, "", []), extra)
            self.assertNotIn("192.168", err.getvalue())

    def test_default_transport_loopback_no_proxy_no_redirect_capped(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        cases = [((200, {}, TAGS), []), ((302, {"Location": "/elsewhere"}, b""), ["http 302"]),
                 ((503, {}, MARK.encode()), ["http 503"]), ((200, {}, b"x" * 300 * 1024), ["bad reply"])]
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9"}):
            for plan, details in cases:
                Server.hits, Server.plan = [], plan
                code, doc, _ = self.run_health("--model", url, "--model-name", "qwen")
                self.assertEqual(([p["detail"] for p in doc["problems"]], Server.hits), (details, ["/api/tags"]))
            server.shutdown()
            server.server_close()
            code, doc, _ = self.run_health("--model", url)
            self.assertEqual((code, doc["problems"]), (1, [{"check": "model", "detail": "unreachable"}]))


if __name__ == "__main__":
    unittest.main()
