"""RF1920-5 tests: editor prepare refuses a too-deep or oversized request cleanly.

A request nested too deep (file or dict) is "request is not valid JSON", never a RecursionError traceback; the CLI
reads a request file only up to 64 KiB + 1 byte and refuses anything but a regular file as one io-error line.
Reuses the throwaway writer repo from test_editor (temp Git repo, linked worktree, private 0700 state dir).
Run: python3 -m unittest hass.tests.test_editor_request_limits -v
"""

import contextlib
import io
import json
import os
from unittest import mock

from hass import editor
from hass.tests.test_editor import NEW_HOURS, EditorTestCase

NOT_JSON = {"result": "invalid", "problems": ["request is not valid JSON"]}
TOO_LARGE = {"result": "invalid", "problems": ["request is larger than 64 KiB"]}
VALID = json.dumps({"ops": [{"op": "store.set_hours", "args": {"hours": NEW_HOURS}}]}).encode("utf-8")


def _deep(levels, leaf):
    """A dict nested `levels` deep, built iteratively (no recursion in the test itself)."""
    for _ in range(levels):
        leaf = {"a": leaf}
    return leaf


class RequestLimitTestCase(EditorTestCase):
    def setUp(self):
        self.r = self.repo()

    def write(self, name, data):
        path = self.r.state.parent / name
        path.write_bytes(data)
        return path

    def run_cli(self, path):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = editor.main(["prepare", str(path), "--state", str(self.r.state)])
        self.assertEqual(err.getvalue(), "")  # no traceback, nothing on stderr
        self.assertEqual(out.getvalue().count("\n"), 1, out.getvalue())
        return code, json.loads(out.getvalue())

    def assertRefused(self, path, expected):
        self.assertEqual(self.run_cli(path), (1, expected))  # exit 1 as for any invalid result
        self.assertEqual(self.r.drafts(), [])


class DeepRequestTests(RequestLimitTestCase):
    def test_deep_file_is_not_valid_json(self):
        for name, data in (("open", b"[" * 60000), ("closed", b"[" * 30000 + b"]" * 30000)):
            with self.subTest(case=name):
                self.assertRefused(self.write(f"{name}.json", data), NOT_JSON)

    def test_deep_dict_is_not_valid_json_and_raises_nothing(self):
        cases = {"5000 deep inside ops": {"ops": [{"op": "store.set_hours", "args": {"hours": _deep(5000, "x")}}]},
                 "100000 deep": _deep(100000, None)}
        for name, request in cases.items():
            with self.subTest(case=name):
                self.assertEqual(editor.prepare(request, state=str(self.r.state)), NOT_JSON)
                self.assertEqual(self.r.drafts(), [])

    def test_deep_bytes_are_not_valid_json(self):
        self.assertEqual(editor.prepare(b"[" * 60000, state=str(self.r.state)), NOT_JSON)
        self.assertEqual(self.r.drafts(), [])


class LargeRequestTests(RequestLimitTestCase):
    def test_one_byte_over_64_kib_is_too_large(self):
        self.assertRefused(self.write("over.json", b" " * (editor.MAX_REQUEST + 1)), TOO_LARGE)

    def test_exactly_64_kib_is_parsed_not_too_large(self):
        self.assertRefused(self.write("edge.json", b" " * editor.MAX_REQUEST), NOT_JSON)

    def test_sparse_1_gib_file_is_too_large_and_never_read_whole(self):
        path = self.write("huge.json", b"")
        os.truncate(path, 1 << 30)
        sizes, real_open = [], open

        class Spy:
            def __init__(self, fh): self.fh = fh
            def __enter__(self): return self
            def __exit__(self, *exc): self.fh.close()
            def read(self, n=-1):
                sizes.append(n)
                return self.fh.read(n)

        def spy_open(p, mode):  # only the request file is spied on; the state config reads as usual
            return Spy(real_open(p, mode)) if str(p) == str(path) else real_open(p, mode)

        with mock.patch.object(editor, "open", create=True, new=spy_open):
            self.assertRefused(path, TOO_LARGE)
        self.assertEqual(sizes, [editor.MAX_REQUEST + 1])


class NonRegularRequestTests(RequestLimitTestCase):
    def assertIoError(self, path, name):
        self.assertEqual(self.run_cli(path), (2, {"result": "io-error", "problems": [name]}))
        self.assertEqual(self.r.drafts(), [])

    def test_folder_is_one_io_error_line(self):
        self.assertIoError(self.r.state.parent, "IsADirectoryError")

    def test_fifo_is_one_io_error_line_and_never_opened(self):
        fifo = self.r.state.parent / "request.fifo"
        os.mkfifo(fifo)
        with mock.patch.object(editor, "open", create=True, side_effect=AssertionError("opened")):
            self.assertIoError(fifo, "ValueError")


class ValidRequestTests(RequestLimitTestCase):
    def test_valid_file_gives_the_same_draft_as_its_bytes(self):
        code, line = self.run_cli(self.write("ok.json", VALID))
        self.assertEqual(code, 0, line)
        draft = line["draft"]
        self.assertEqual(draft["change_id"], "chg-" + draft["draft_hash"][7:19])
        self.assertEqual(self.r.drafts(), [draft["change_id"] + ".json"])
        self.assertEqual(editor.prepare(VALID, state=str(self.r.state)), line)  # same draft, no second one
        self.assertEqual(self.r.drafts(), [draft["change_id"] + ".json"])
