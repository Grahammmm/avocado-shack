"""Offline CLI contract tests using invented pilot captures and values."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_private_scan.py"
SPEC = importlib.util.spec_from_file_location("pilot_private_scan", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


class PilotPrivateScanTests(unittest.TestCase):
    def setUp(self):
        with_root = tempfile.TemporaryDirectory()
        self.addCleanup(with_root.cleanup)
        self.root = Path(with_root.name)
        self.private = self.fixture("operator-list.txt", "\n 3.50 \n47\n8102203\n")

    def fixture(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def scan(self, *options, private=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = SCAN.main(["--private", str(private or self.private), *map(str, options)])
        return status, out.getvalue(), err.getvalue()

    def test_public_price_is_not_a_hit_in_cli(self):
        # Using the generic money rejection rule would fail this direct invocation.
        card = self.fixture("card.html", "<p>Public price: $6.75 each</p>")
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--private", str(self.private), "--html", str(card)],
            cwd=self.root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "card.html: clean\n", ""))

    def test_repeatable_inputs_count_hits_without_echoing_values_or_context(self):
        # A digit-only scanner misses the spoken cost; a set of hits undercounts
        # occurrences. Full stream equality excludes values, context and paths.
        digit = self.fixture("first.txt", "synthetic cost $3.500; callback marker 8102203")
        words = self.fixture("second.txt", "invented quote: three fifty; correction: three fifty")
        card = self.fixture("card.html", '<img alt="invented tally: 47">')
        clean = self.fixture("control.html", "<p>Tally: 470; price $6.75 each</p>")
        self.assertEqual(self.scan("--text", digit, "--text", words, "--html", card, "--html", clean),
                         (1, "first.txt: private-number (2)\nsecond.txt: private-number (2)\n"
                          "card.html: private-number (1)\ncontrol.html: clean\n", ""))

    def test_html_preserves_inline_readings_and_scans_labels(self):
        # Joining nodes with spaces misses split digits; skipping labels or
        # scanning undecoded references misses values shown in the card.
        card = self.fixture("card.html", '<p>4<b>7</b></p><p>three\n<span>fifty</span></p>'
                            '<img alt="&#52;7" title="4&#55;" aria-label="47">')
        self.assertEqual(self.scan("--html", card), (1, "card.html: private-number (5)\n", ""))

    def test_html_ignores_code_comments_and_unrelated_attributes(self):
        # A raw HTML scan, or a projection that glues blocks or labels together,
        # can invent hits that never appear in the rendered card.
        card = self.fixture("card.html", '<script>47</script><style>.test{width:47px}</style>'
                            '<!--47--><div data-test="47">three</div><div>fifty</div>'
                            '<img alt="three" title="fifty">')
        self.assertEqual(self.scan("--html", card), (0, "card.html: clean\n", ""))

    def test_private_list_errors_never_echo_path_or_bad_line(self):
        # Silently dropping malformed rows would certify an incomplete scan.
        missing = self.root / "private-path-marker.txt"
        blank = self.fixture("blank.txt", " \n\t\n")
        malformed = self.fixture("malformed.txt", "47\nprivate-row-marker 8102203\n")
        undecodable = self.root / "invalid.txt"
        undecodable.write_bytes(b"\xff")
        for path in (missing, blank, malformed, undecodable):
            with self.subTest(case=path.name):
                self.assertEqual(self.scan(private=path),
                                 (2, "", "error: private list must be readable and contain decimal numbers\n"))

    def test_unreadable_capture_takes_precedence_over_hit(self):
        # A later hit must not overwrite input-error status or leak a bad path.
        bad_html = self.root / "8102203.html"
        bad_html.write_bytes(b"\xff")
        card = self.fixture("card.html", "<p>synthetic 47</p>")
        self.assertEqual(self.scan("--text", self.root / "8102203.txt", "--html", bad_html, "--html", card),
                         (2, "card.html: private-number (1)\n", "error: could not read captured input as UTF-8\n" * 2))

    def test_private_number_in_basename_is_redacted(self):
        # A status-only report can still leak through a bad filename.
        reply = self.fixture("8102203.txt", "invented 47")
        self.assertEqual(self.scan("--text", reply), (1, "[redacted filename]: private-number (1)\n", ""))
