#!/usr/bin/env python3
"""Check a pilot card's PNG structure and report its SHA-256 without decoding pixels."""

import argparse
import hashlib
from pathlib import Path
import struct
import sys
import zlib


SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Incomplete(ValueError):
    """A fixed PNG failure reason safe to report to the operator."""


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse diagnostics can contain supplied paths or digest values.
        self.exit(2, "error: invalid arguments (see --help)\n")


def dimensions(raw):
    if not raw.startswith(SIGNATURE):
        raise Incomplete("truncated" if raw and SIGNATURE.startswith(raw) else "not-png")
    view = memoryview(raw)
    offset = len(SIGNATURE)
    size = None
    has_idat = False
    while offset < len(raw):
        if len(raw) - offset < 12:  # length, type and CRC, even with no payload
            raise Incomplete("truncated")
        length, kind = struct.unpack_from(">I4s", view, offset)
        end = offset + 8 + length  # CRC follows the payload
        if end + 4 > len(raw):
            raise Incomplete("truncated")
        (crc,) = struct.unpack_from(">I", view, end)
        if zlib.crc32(view[offset + 4:end]) != crc:
            raise Incomplete("bad-crc")

        if size is None:
            if kind != b"IHDR" or length != 13:
                raise Incomplete("no-ihdr")
            size = struct.unpack_from(">II", view, offset + 8)
            if 0 in size:
                raise Incomplete("no-ihdr")
        elif kind == b"IDAT":
            has_idat = True
        elif kind == b"IEND":
            if length:
                raise Incomplete("no-iend")  # A valid end marker has no payload.
            if not has_idat:
                raise Incomplete("no-idat")
            if end + 4 != len(raw):
                raise Incomplete("trailing-bytes")
            return size
        offset = end + 4
    raise Incomplete("no-ihdr" if size is None else "no-iend")


def main(argv=None):
    parser = PrivateArgumentParser(prog="pilot_card_png.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--png", required=True, type=Path, metavar="FILE")
    parser.add_argument("--expect-sha256", metavar="HEX", help="compare against the full SHA-256")
    parser.add_argument("--full", action="store_true", help="print full SHA-256 for the private receipt")
    args = parser.parse_args(argv)
    try:
        # Validate and hash the same bytes, without reopening the capture.
        raw = args.png.read_bytes()
    except (OSError, ValueError):
        print("INCOMPLETE not-png")
        return 1
    try:
        width, height = dimensions(raw)
    except Incomplete as error:
        print(f"INCOMPLETE {error}")
        return 1

    digest = hashlib.sha256(raw).hexdigest()
    if args.expect_sha256 is not None and args.expect_sha256.lower() != digest:
        print("DIGEST-MISMATCH")
        return 1
    print(f"COMPLETE {width}x{height} sha256 {digest if args.full else digest[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
