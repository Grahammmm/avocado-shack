"""Hass product photo op (H10 part 3): ``product.set_photo`` puts a stored photo's web copy on a product.

The photo is named by the sha256 of an original in the private media store (settings ``mediaRoot``). The op makes the
metadata-free web copy (``media.web_copy``), points the product's ``image`` at
``assets/products/photo-<sha[:16]>.<ext>`` and sets ``imageAlt``; the editor writes that file and commits it with the
content change. Undo restores the old image; the committed photo file stays, unreferenced. No resizing, conversion or
deletion of old photo files. ``imageAlt`` must say what the photo shows: a file name, camera default name, placeholder
word, a placeholder word with only an article or number, the photo id, fewer than 3 letters, a screenshot or
messaging-app default name, or a web link is refused before the media store is read; so is one over 200 characters
(``MAX_ALT``, the content-model limit).
"""

from __future__ import annotations

import copy
import os
import re
import stat
from pathlib import Path

from hass import editor, media
from hass.content_model import TEXT_LIMITS
from hass.ops import Arg, Op, Refused, Touched
from hass.ops.catalog import _product

_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff")
_CAMERA_RE = re.compile(r"^(?:(?:img|dsc|dscn|pxl|photo|image)[_ -]?\d{2,}|img[_ -]?e\d{3,}|(?:mvimg|pano)[_ -]?\d{6,}"
                        r"|_dsc\d{3,}|gopr\d{3,}|g[xh]\d{5,}|dji[_ -]?\d{3,}|p\d{7})")
_APP_DEFAULT_RE = re.compile(r"^(screenshot|screen shot|screen recording|whatsapp image|signal)[ _-]*\d{4}[-_.]?\d{2}[-_.]?\d{2}")
_BARE_SCREEN_RE = re.compile(r"^(screenshot|screen shot)( ?\(\d{1,3}\))?$")
_PLACEHOLDERS = {"photo", "image", "picture", "pic", "img", "product", "product photo", "alt", "n/a", "na", "none", "todo",
                 "tbd"}
_PLACEHOLDER_RE = re.compile(r"^(?:(?:a|an|the|my|our|this)\s+)?(?:product\s+)?(?:photo|image|picture|pic|img|product)(?:\s*(?:#|no\.?)?\s*\d{1,3})?[\s.!]*$")  # noqa: E501
MAX_ALT = TEXT_LIMITS["product"]["imageAlt"]
FOLDER_REPLY = "the site photo folder is unusable"
ALT_REPLY = ("imageAlt should say what the photo shows (for example \"Hass avocados in a wooden crate\"), "
             "not a file name or placeholder")


def _alt_problem(alt, sha):
    """The fixed owner reply when ``alt`` is a file name, camera name, placeholder, the photo id or too short."""
    folded = alt.strip().casefold()
    if (folded.endswith(_IMAGE_EXT) or _CAMERA_RE.match(folded) or folded in _PLACEHOLDERS
            or sha[:12].casefold() in folded or sum(c.isalpha() for c in folded) < 3
            or _APP_DEFAULT_RE.match(folded) or _BARE_SCREEN_RE.match(folded)
            or "://" in folded or folded.startswith("www.") or _PLACEHOLDER_RE.match(folded)):
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


def _folder_unusable(site_dir):
    """True when ``assets`` or ``assets/products`` under the site exists as a symlink or non-directory (never followed).
    Missing folders are fine: the editor creates them."""
    for folder in ("assets", "assets/products"):
        try:
            mode = os.lstat(Path(site_dir) / folder).st_mode
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if not stat.S_ISDIR(mode):
            return True
    return False


def install(ctx, sha, alt):
    """Queue the stored photo's web copy for commit; the site path ``assets/products/photo-<sha16>.<ext>`` or Refused.
    Shared by product.set_photo and product.add (AV0022-02). Same bytes already there are reused, not rewritten."""
    if not media.SHA_RE.fullmatch(sha):
        return Refused("photo must be a stored photo id")
    if len(alt) > MAX_ALT:  # before _alt_problem: one reply; counts characters, same limit as the content model
        return Refused(f"the photo description is longer than {MAX_ALT} characters (it has {len(alt)})")
    problem = _alt_problem(alt, sha)
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
    path, have, link = Path(ctx.site_dir) / target, ctx.assets.get(target), False
    try:  # read the site file only when not already queued; lstat first so a FIFO is never opened
        if target not in ctx.assets:
            if _folder_unusable(ctx.site_dir):
                return Refused(FOLDER_REPLY)
            mode = os.lstat(path).st_mode
            link = stat.S_ISLNK(mode)
            if not (link or stat.S_ISREG(mode)):
                return Refused("the website photo file cannot be read")
            have = None if link else path.read_bytes()
    except FileNotFoundError:
        pass
    except OSError:  # fixed reply: no path or exception text
        return Refused("the website photo file cannot be read")
    if link or (have is not None and have != data):
        return Refused("a different photo already uses that name")
    if have is None:
        ctx.assets[target] = data
    return target


def _set_photo(content, args, ctx):
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    target = install(ctx, args["photo"], args["imageAlt"])
    if isinstance(target, Refused):
        return target
    before = copy.deepcopy(product)
    product.update(image=target, imageAlt=args["imageAlt"])
    if product == before:
        return Refused(f"{args['id']} already shows that photo with that imageAlt")
    return [Touched("products", args["id"], before, copy.deepcopy(product))]


OPS = (Op("product.set_photo", {"id": Arg("id"), "photo": Arg("id"), "imageAlt": Arg("text")}, _set_photo),)
