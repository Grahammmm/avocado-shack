"""Exercise install-switch readback on disposable, synthetic JSON only."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.hass import install_switch_readback


OFF = '{"settings":{"npp":false},"preserved":{"enabled":true}}'
ON = '{"settings":{"npp":true,"houseRender":true,"photo_polish":true},"preserved":{"enabled":true}}'
SENTINEL = "synthetic-private-canary"


class InstallSwitchReadbackTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.backup = root / "backup.json"
        self.candidate = root / "candidate.json"
        self.argv = ["--before", str(self.backup), "--after", str(self.candidate)]

    def check(self, before, after, *, difference=None, diagnostic=None):
        self.backup.write_bytes(before.encode() if isinstance(before, str) else before)
        self.candidate.write_bytes(after.encode() if isinstance(after, str) else after)
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = install_switch_readback.main(self.argv)
        if difference is None:
            self.assertEqual((status, stdout.getvalue(), stderr.getvalue()), (
                0, 'PASS "/settings/npp" "/settings/houseRender" "/settings/photo_polish"\n', "",
            ))
        else:
            self.assertEqual((status, stdout.getvalue()), (1, ""))
            self.assertTrue(stderr.getvalue().endswith(f" at {json.dumps(difference)}\n"), stderr.getvalue())
            if diagnostic:
                self.assertTrue(stderr.getvalue().startswith(diagnostic), stderr.getvalue())
        self.assertNotIn(SENTINEL, stdout.getvalue() + stderr.getvalue())

    def test_inserts_absent_switches_and_accepts_reordered_objects(self):
        # Byte/dict-order comparisons would reject this otherwise exact edit.
        self.check(
            '{"settings":{},"other":[{"a":null,"b":1.0}]}',
            '{"other":[{"b":1e0,"a":null}],"settings":{"photo_polish":true,"houseRender":true,"npp":true}}',
        )
        self.check(OFF, ON)
        # The two other switches may already be true; only npp has a baseline precondition.
        self.check('{"settings":{"npp":false,"houseRender":true,"photo_polish":true},'
                   '"preserved":{"enabled":true}}', ON)

    def test_requires_baseline_npp_off(self):
        # A truthiness check would silently admit false-like non-booleans.
        for value in (True, None, 0, 0.0, "", "false", [], {}):
            with self.subTest(value=value):
                self.check(json.dumps({"settings": {"npp": value}}), ON,
                           difference="/settings/npp", diagnostic="FAIL before:")

    def test_requires_baseline_settings_object(self):
        # Do not repair or create a container outside the three allowed keys.
        for before, path in (("[]", ""), ("{}", "/settings"), ('{"settings":null}', "/settings"),
                             ('{"settings":[]}', "/settings")):
            with self.subTest(before=before):
                self.check(before, ON, difference=path, diagnostic="FAIL before:")

    def test_requires_all_three_literal_booleans(self):
        # Identity and presence are required at each key, not Python equality/truthiness.
        for key in ("npp", "houseRender", "photo_polish"):
            for value in (1, 1.0, False, "true", None):
                with self.subTest(key=key, value=value):
                    after = json.loads(ON)
                    if value is None:
                        del after["settings"][key]
                    else:
                        after["settings"][key] = value
                    self.check(OFF, json.dumps(after), difference=f"/settings/{key}")

    def test_detects_unrelated_changes_even_with_all_switches_on(self):
        # A switch projection misses other edits, including nested Python-equal types.
        for old, new, path in (
            ('true', '1', ''), ('0', 'false', ''), ('1', '1.0', ''), ('true', '1.0', ''),
            ('null', 'false', ''), ('[]', '{}', ''), ('1', '"1"', ''),
            ('[{"x":true}]', '[{"x":1}]', '/0/x'),
            ('[1,2]', '[2,1]', '/0'), ('[1]', '[1,2]', '/1'), ('[1,2]', '[1]', '/1'),
            ('{}', '{"added":1}', '/added'), ('{"removed":1}', '{}', '/removed'),
            ('1.0000000000000000001', '1.0000000000000000002', ''),
            ('1e400', '2e400', ''), ('1e-400', '2e-400', ''),
        ):
            with self.subTest(old=old, new=new):
                self.check(OFF[:-1] + ',"other":' + old + '}', ON[:-1] + ',"other":' + new + '}',
                           difference="/other" + path)
        self.check(OFF, ON.replace('"houseRender"', '"added":null,"houseRender"'),
                   difference="/settings/added")
        self.check(OFF, '[]', difference="")

    def test_refuses_ambiguous_or_invalid_json_in_either_input(self):
        # Last-key-wins and Python's non-standard constants must not normalize invalid inputs.
        for fragment, reason in (
            ('{"x":1,"x":1}', 'duplicate JSON key'),
            (r'[{"x":1,"\u0078":2}]', 'duplicate JSON key'),
            ('NaN', 'non-JSON number'), ('Infinity', 'non-JSON number'), ('-Infinity', 'non-JSON number'),
            (f'"{SENTINEL}', 'invalid JSON'), (b'"\xff"', 'invalid JSON'),
        ):
            for side, document in (("before", OFF), ("after", ON)):
                with self.subTest(side=side, reason=reason, fragment=fragment):
                    raw = (document[:-1] + ',"other":').encode()
                    raw += fragment.encode() if isinstance(fragment, str) else fragment
                    raw += b'}'
                    self.check(raw if side == "before" else OFF, raw if side == "after" else ON,
                               difference="", diagnostic=f"FAIL {side}: {reason}")
        duplicate = ON.replace('"npp":true', '"npp":false,"npp":true')
        self.check(OFF, duplicate, difference="", diagnostic="FAIL after: duplicate JSON key")

    def test_diagnostic_escapes_keys_without_printing_values(self):
        # A key with a slash, tilde or newline must still identify a single path.
        before, after = json.loads(OFF), json.loads(ON)
        before["line\n/~"] = SENTINEL + "-before"
        after["line\n/~"] = SENTINEL + "-after"
        self.check(json.dumps(before), json.dumps(after), difference="/line\n~1~0")

    def test_cli_reads_both_files_without_editing_them_or_echoing_argv(self):
        # Verify the actual script entrypoint, unchanged input bytes and redacted I/O/usage errors.
        self.backup.write_text(OFF, encoding="utf-8")
        self.candidate.write_text(ON, encoding="utf-8")
        command = [sys.executable, "-B", install_switch_readback.__file__]
        result = subprocess.run(command + self.argv, capture_output=True, text=True, check=True)
        self.assertTrue(result.stdout.startswith("PASS "))
        self.assertEqual(result.stderr, "")
        self.assertEqual((self.backup.read_bytes(), self.candidate.read_bytes()), (OFF.encode(), ON.encode()))
        result = subprocess.run(command + self.argv[:-1] + [str(self.candidate.with_name(SENTINEL))],
                                capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", 'FAIL after: cannot read input at ""\n'))
        result = subprocess.run(command + self.argv + [SENTINEL], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertNotIn(SENTINEL, result.stderr)
