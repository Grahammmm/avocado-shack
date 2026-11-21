"""Fixture-only CLI tests for the pilot card completeness receipt."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_card_png.py"
SPEC = importlib.util.spec_from_file_location("pilot_card_png", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def chunk(kind, payload=b""):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def header(width, height):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))


SIGNATURE = b"\x89PNG\r\n\x1a\n"
IHDR = header(2, 3)
TEXT = chunk(b"tEXt", b"Comment\x00synthetic-payload-marker")
IDAT = chunk(b"IDAT", zlib.compress(b"\x00\x10\x20" * 3))
IEND = chunk(b"IEND")
PNG = SIGNATURE + IHDR + TEXT + IDAT + IEND
DIGEST = hashlib.sha256(PNG).hexdigest()


class PilotCardPngTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "synthetic-filename-marker.png"

    def invoke(self, raw, *options):
        if raw is not None:
            self.path.write_bytes(raw)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = CHECKER.main(["--png", str(self.path), *options])
        if raw is not None:
            self.assertEqual(self.path.read_bytes(), raw)
        return code, out.getvalue(), err.getvalue()

    def test_script_entrypoint_reports_dimensions_and_only_short_digest_by_default(self):
        # A missing entry point, swapped dimensions, or unredacted digest breaks the receipt.
        self.path.write_bytes(PNG)
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--png", str(self.path)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, f"COMPLETE 2x3 sha256 {DIGEST[:12]}\n", ""))

    def test_matching_expectation_does_not_enable_full_output(self):
        # Comparing full SHA-256 must not implicitly disclose it, even when supplied in uppercase.
        self.assertEqual(self.invoke(PNG, "--expect-sha256", DIGEST.upper()),
                         (0, f"COMPLETE 2x3 sha256 {DIGEST[:12]}\n", ""))
        self.assertEqual(self.invoke(PNG, "--full", "--expect-sha256", DIGEST),
                         (0, f"COMPLETE 2x3 sha256 {DIGEST}\n", ""))

    def test_mismatched_or_invalid_expectation_never_echoes_either_value(self):
        # Same prefix but different full hash catches prefix-only comparison.
        wrong = DIGEST[:-1] + ("0" if DIGEST[-1] != "0" else "1")
        for label, expected in (("different suffix", wrong), ("prefix only", DIGEST[:12]),
                                ("invalid", "synthetic-expectation-marker"), ("empty", "")):
            with self.subTest(label=label):
                self.assertEqual(self.invoke(PNG, "--full", "--expect-sha256", expected),
                                 (1, "DIGEST-MISMATCH\n", ""))

    def test_invalid_cli_does_not_echo_arguments_or_abbreviate_full(self):
        # Stock argparse can quote rejected arguments or accept --ful as --full.
        self.path.write_bytes(PNG)
        for option in ("--ful", "synthetic-argument-marker"):
            with self.subTest(option=option):
                with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                    with self.assertRaises(SystemExit) as raised:
                        CHECKER.main(["--png", str(self.path), option])
                self.assertEqual((raised.exception.code, out.getvalue(), err.getvalue()),
                                 (2, "", "error: invalid arguments (see --help)\n"))

    def test_wrong_signature_and_unreadable_path_fail_without_private_values(self):
        # Neither a file-open diagnostic nor bad file bytes belong in the output.
        for label, raw in (("missing", None), ("empty", b""), ("wrong signature", b"synthetic-payload-marker")):
            with self.subTest(label=label):
                self.assertEqual(self.invoke(raw, "--full"), (1, "INCOMPLETE not-png\n", ""))

    def test_partial_signature_chunk_header_payload_and_crc_are_truncated(self):
        # Do not confuse mid-chunk EOF with a clean chunk boundary lacking IEND.
        prefix = SIGNATURE + IHDR + TEXT
        for label, raw in (("signature", SIGNATURE[:5]), ("chunk header", prefix + IDAT[:6]),
                           ("chunk payload", prefix + IDAT[:9]), ("chunk CRC", PNG[:-1])):
            with self.subTest(label=label):
                self.assertEqual(self.invoke(raw), (1, "INCOMPLETE truncated\n", ""))

    def test_crc_checked_for_every_chunk_including_ancillary_and_end(self):
        # Skipping a chunk CRC, or comparing the digest before structural checks, breaks this.
        chunks = [IHDR, TEXT, IDAT, IEND]
        for index, kind in enumerate(("IHDR", "tEXt", "IDAT", "IEND")):
            with self.subTest(kind=kind):
                damaged = chunks.copy()
                damaged[index] = chunks[index][:-1] + bytes([chunks[index][-1] ^ 1])
                self.assertEqual(self.invoke(SIGNATURE + b"".join(damaged), "--expect-sha256", DIGEST),
                                 (1, "INCOMPLETE bad-crc\n", ""))

    def test_requires_a_well_framed_ihdr_first_and_nonzero_dimensions(self):
        # Merely finding IHDR anywhere, or reading nonzero width alone, would accept these.
        for label, raw in (("absent", SIGNATURE), ("wrong order", SIGNATURE + TEXT + IHDR + IDAT + IEND),
                           ("short IHDR", SIGNATURE + chunk(b"IHDR", struct.pack(">II", 2, 3)) + IDAT + IEND),
                           ("zero width", SIGNATURE + header(0, 3) + IDAT + IEND),
                           ("zero height", SIGNATURE + header(2, 0) + IDAT + IEND)):
            with self.subTest(label=label):
                self.assertEqual(self.invoke(raw), (1, "INCOMPLETE no-ihdr\n", ""))

    def test_required_chunks_and_exact_end(self):
        # CRC-valid records alone are insufficient; do not stop early and ignore appended data.
        for reason, raw in (("no-idat", SIGNATURE + IHDR + TEXT + IEND),
                            ("no-iend", PNG[:-len(IEND)]),
                            ("no-iend", PNG[:-len(IEND)] + chunk(b"IEND", b"nonempty")),
                            ("trailing-bytes", PNG + b"synthetic-trailing-marker")):
            with self.subTest(reason=reason):
                self.assertEqual(self.invoke(raw, "--full"), (1, f"INCOMPLETE {reason}\n", ""))
