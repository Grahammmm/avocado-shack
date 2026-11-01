"""Hass product photo op (H10 part 3): ``product.set_photo`` puts a stored photo's web copy on a product.

The photo is named by the sha256 of an original in the private media store (settings ``mediaRoot``). The op makes the
metadata-free web copy (``media.web_copy``), points the product's ``image`` at
``assets/products/photo-<sha[:16]>.<ext>`` and sets ``imageAlt``; the editor writes that file and commits it with the
content change. Undo restores the old image; the committed photo file stays, unreferenced. No resizing, conversion or
deletion of old photo files. ``imageAlt`` must say what the photo shows: a file name, camera default name, placeholder
word, the photo id or fewer than 3 letters is refused before the media store is read.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from hass import editor, media
from hass.ops import Arg, Op, Refused, Touched
from hass.ops.catalog import _product

_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff")
_CAMERA_RE = re.compile(r"^(img|dsc|dscn|pxl|photo|image)[_ -]?\d{2,}")
_PLACEHOLDERS = {"photo", "image", "picture", "pic", "img", "product", "product photo", "alt", "n/a", "na", "none", "todo",
                 "tbd"}
ALT_REPLY = ("imageAlt should say what the photo shows (for example \"Hass avocados in a wooden crate\"), "
             "not a file name or placeholder")


def _alt_problem(alt, sha):
    """The fixed owner reply when ``alt`` is a file name, camera name, placeholder, the photo id or too short."""
    folded = alt.strip().casefold()
    if (folded.endswith(_IMAGE_EXT) or _CAMERA_RE.match(folded) or folded in _PLACEHOLDERS
            or sha[:12].casefold() in folded or sum(c.isalpha() for c in folded) < 3):
        return ALT_REPLY
    return None


def _web_bytes(root, sha):
    """(bytes, ext) of the photo's web copy, or Refused with the fixed owner reply."""
    try:
        out = media.web_copy(root, sha)
        return Path(out["path"]).read_bytes(), media.EXT[out["kind"]]
    except media.Refused as exc:
        return Refused(exc.reply)
    except editor.UnsafeState as exc:  # fixed messages only: no path in them
        return Refused(f"photo store is unusable: {exc}")


def _set_photo(content, args, ctx):
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    sha = args["photo"]
    if not media.SHA_RE.fullmatch(sha):
        return Refused("photo must be a stored photo id")
    problem = _alt_problem(args["imageAlt"], sha)
    if problem:
        return Refused(problem)
    root = ctx.settings.get("mediaRoot")
    if not root:
        return Refused("photo store is not configured")
    found = _web_bytes(root, sha)
    if isinstance(found, Refused):
        return found
    data, ext = found
    target = f"assets/products/photo-{sha[:16]}.{ext}"
    path = Path(ctx.site_dir) / target
    have = ctx.assets.get(target, path.read_bytes() if path.is_file() and not path.is_symlink() else None)
    if path.is_symlink() or (have is not None and have != data):
        return Refused("a different photo already uses that name")
    if have is None:
        ctx.assets[target] = data
    before = copy.deepcopy(product)
    product.update(image=target, imageAlt=args["imageAlt"])
    if product == before:
        return Refused(f"{args['id']} already shows that photo with that imageAlt")
    return [Touched("products", args["id"], before, copy.deepcopy(product))]


OPS = (Op("product.set_photo", {"id": Arg("id"), "photo": Arg("id"), "imageAlt": Arg("text")}, _set_photo),)
