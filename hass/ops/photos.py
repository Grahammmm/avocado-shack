"""Hass product photo op (H10 part 3): ``product.set_photo`` puts a stored photo's web copy on a product.

The photo is named by the sha256 of an original in the private media store (settings ``mediaRoot``). The op makes the
metadata-free web copy (``media.web_copy``), points the product's ``image`` at
``assets/products/photo-<sha[:16]>.<ext>`` and sets ``imageAlt``; the editor writes that file and commits it with the
content change. Undo restores the old image; the committed photo file stays, unreferenced. No resizing, conversion or
deletion of old photo files. ``imageAlt`` must say what the photo shows: a file name, camera default name, placeholder
word, a placeholder word with only an article or number, the photo id, fewer than 3 letters, a screenshot or
messaging-app default name, or a web link is refused before the media store is read; so is one over 200 characters
(``MAX_ALT``, the content-model limit). A file-system error (``OSError``) making or reading the stored photo's web
copy gives the one fixed reply ``STORE_UNREADABLE`` and writes nothing.

SKILLS-PIC-1 (house-style render, behind a flag): with ``houseRender`` true in the settings, ``install`` does not copy the
owner's pixels but the site-standard picture made by ``newitem_render.render`` (800x800 warm ivory, subject about 90 %,
soft shadow, JPEG, no metadata), always named ``assets/products/photo-<sha16>.jpg`` (D1; the page labels it a photo). The
same input gives the same bytes, so the previewed bytes are the committed bytes. A photo that cannot be made house-style
(busy background, too dark, blurry, too small, or the finished picture fails ``house_style.check_image``) is NOT installed
and NOT faked: ``install`` returns ``Retake`` (a ``Refused`` whose ``reason`` is a plain sentence asking for a retake and
whose ``problems`` names every defect found). With the flag off (the default), absent or anything but ``True``, the bytes
are exactly what they were before. The home page hero photo asks for ``style=False`` and keeps today's behaviour (D6).

HASS-IMAGE-1 (behind ``photo_polish``, which needs ``houseRender``): when ``photo_polish`` settled a cleaned picture for
this photo (it passed the fidelity gate), that picture is published instead of the house render, also for a photo the
house render alone would have asked to retake. In every other case (not run, still running, failed, rejected) install
does exactly what it did before, and that choice is settled so prepare, apply and verify agree.
"""

from __future__ import annotations

import copy
import functools
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from hass import editor, house_style, media, newitem_render, photo_polish
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
STORE_UNREADABLE = "the stored photo cannot be read right now; nothing was changed"
ALT_REPLY = ("imageAlt should say what the photo shows (for example \"Hass avocados in a wooden crate\"), "
             "not a file name or placeholder")


HOUSE_FLAG = "houseRender"  # settings key; only the JSON value true turns the house render on
MAKE_FAILED = "I can't make that picture right now, so nothing was changed. Please send the photo again in a few minutes."
ALREADY_RAW = "That photo is already on the website the way it came, so I can't change how it looks."
RETAKE = {  # defect code -> the plain sentence for Mike (docs/hass/VOICE.md: short, nothing technical, one next step)
    "busy": "The background behind it is too busy for me to make a clean picture. Could you take it again on a plain surface, like a counter or a sheet?",
    "dark": "That photo is too dark. Could you take it again in better light?",
    "blurry": "That photo is a bit blurry. Could you take it again, holding the phone steady?",
    "small": "That photo is too small, so the picture would look soft. Could you take it again a bit closer?",
    "style": "I couldn't make that photo look like the others on the website. Could you take it again on a plain surface in good light?",
}
RENDER_REPLY = {  # newitem_render's own refusals, in the owner's voice (its fixed texts are for a drafting tool, not for him)
    "too-many-pixels": "That photo is too big for me to open. Could you send a smaller copy, or a screenshot of it?",
    "blank": "I couldn't find the item in that photo. Could you send another one?",
    "too-narrow": "That photo is a thin strip, so I can't use it. Could you send an ordinary photo of the item?",
    "unreadable": media.REPLIES["unreadable"],
}
ORDER = ("busy", "dark", "blurry", "small", "style")  # which defect is told first when there are several
SHARP_MIN = 0.14  # edge sharpness (see _sharpness): the synthetic set measured 0.21 or more sharp, 0.13 or less blurred by 4 px
CACHE = 8


@dataclass
class Retake(Refused):
    """A photo the house render will not stand behind. ``reason`` is the plain sentence for the owner; ``problems`` lists
    every defect code found, in the order of ORDER."""
    problems: tuple = ()


def _sharpness(img, alpha=None):
    """Edge sharpness of an upright RGB image: the strongest 0.5 % of one-pixel steps, as a share of the picture's own light
    range, on a 640 px copy. A sharp edge changes within a pixel or two; a soft one spreads out, so the share falls.

    With ``alpha`` (a supplied cut-out) only the inside of the product counts: its cut edge is sharp whatever the focus, so
    the steps and the light range are taken where the 5 px neighbourhood is fully opaque. A cut-out with too little inside
    to judge gives 0.0 (not sharp), never a pass by default."""
    _Image, _ops, ImageChops, _draw, _enh, ImageFilter = newitem_render._modules()
    box = newitem_render._resample(_Image, "BOX")
    gray = img.convert("L")
    gray.thumbnail((640, 640), box)
    w, h = gray.size
    if w < 8 or h < 8:
        return None
    flat = gray.crop((0, 0, w - 1, h - 1))
    step = ImageChops.lighter(ImageChops.difference(flat, gray.crop((1, 0, w, h - 1))),
                              ImageChops.difference(flat, gray.crop((0, 1, w - 1, h))))
    if alpha is None:
        steps, light = sorted(step.getdata()), sorted(gray.getdata())
    else:
        inner = alpha.resize(gray.size, box).point(lambda v: 255 if v > 250 else 0).filter(ImageFilter.MinFilter(5))
        keep = inner.crop((0, 0, w - 1, h - 1))
        steps = sorted(v for v, m in zip(step.getdata(), keep.getdata()) if m)
        light = sorted(v for v, m in zip(gray.getdata(), inner.getdata()) if m)
        if len(steps) < 400:
            return 0.0
    n = len(steps)
    m = len(light)
    return steps[int(n * .995)] / max(1, light[int(m * .99)] - light[int(m * .01)])


def _problems(data, made, spec):
    """The defect codes of one render, from the render's own report, its finished check and the original's sharpness."""
    report, found = made["report"], set()
    if report.get("isolation") != "cutout":
        found.add("busy")
    elif report["scale"] > newitem_render.MAX_UPSCALE:  # the product is so small it would be enlarged past the limit
        found.add("small")
    luma = report.get("subject_luma")
    if luma is not None and luma * report.get("exposure_gain", 1) < spec["pictures"]["catalog"]["metrics"]["subject_luma"]["min"]:
        found.add("dark")  # even after the render's gentle exposure lift the product is darker than any catalog picture
    img, alpha, _turned = newitem_render._upright(data)
    sharp = _sharpness(img, alpha)  # a cut-out is judged on the inside of the product, not on its cut edge
    if sharp is not None and sharp < SHARP_MIN:
        found.add("blurry")
    if not found and not made["check"]["pass"]:
        found.add("style")
    return tuple(code for code in ORDER if code in found)


@functools.lru_cache(maxsize=CACHE)
def _house(data):
    """Render once per distinct photo: prepare, apply and verify all ask for the same bytes."""
    spec = house_style.load_spec()
    made = newitem_render.render(data, spec)
    return {"jpeg": made["jpeg"], "report": made["report"], "check": made["check"], "problems": _problems(data, made, spec)}


def house_picture(data):
    """The house-style verdict for the bytes of one JPEG or PNG photo (the metadata-free web copy is the intended input).

    {"ok": bool, "jpeg": bytes, "problems": [codes], "reason": plain sentence or None, "report": {...}, "check": {...}}.
    ``jpeg`` is always the best picture the render could make (``ok`` False means it is a fallback that must not be
    installed without a retake). Raises ``media.Refused`` or ``newitem_render.Refused`` (each carries a plain ``.reply``)
    for a photo that cannot be read or is unsafe, and ``house_style.PillowMissing`` when Pillow is not installed."""
    done = _house(data)
    problems = done["problems"]
    return {"ok": not problems, "jpeg": done["jpeg"], "problems": list(problems),
            "reason": RETAKE[problems[0]] if problems else None, "report": copy.deepcopy(done["report"]),
            "check": copy.deepcopy(done["check"])}


def house_check(settings, sha):
    """house_picture for a stored photo (its sha256 in the media store of ``settings``): the verdict dict, or Refused with
    the plain reason the photo cannot be read. For the skill's preview: it asks for a retake before anything is drafted."""
    root = settings.get("mediaRoot")
    if not isinstance(sha, str) or not media.SHA_RE.fullmatch(sha):
        return Refused("photo must be a stored photo id")
    if not root:
        return Refused("photo store is not configured")
    found = _web_bytes(root, sha)
    if isinstance(found, Refused):
        return found
    return _verdict(found[0])


def _verdict(data):
    try:
        return house_picture(data)
    except media.Refused as exc:
        return Refused(exc.reply)
    except newitem_render.Refused as exc:
        return Refused(RENDER_REPLY[exc.code])
    except (house_style.PillowMissing, OSError, MemoryError):  # one fixed reply: no path or library text
        return Refused(MAKE_FAILED)


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
    except OSError:  # web copy not writable or readable: one fixed reply, no path, errno text or photo id
        return Refused(STORE_UNREADABLE)


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


def install(ctx, sha, alt, *, style=True, owner_fallback=False):
    """Queue the stored photo's web copy for commit; the site path ``assets/products/photo-<sha16>.<ext>`` or Refused.
    Shared by product.set_photo and product.add (AV0022-02). Same bytes already there are reused, not rewritten.
    With settings ``houseRender`` true and ``style`` True the queued bytes are the house-style JPEG instead (named .jpg),
    or ``Retake`` when the photo cannot be made house-style. ``style=False`` (the home hero) never renders."""
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
    house = style and ctx.settings.get(HOUSE_FLAG) is True
    cleaned = None
    if house and photo_polish.enabled(ctx.settings):  # HASS-IMAGE-1: the settled cleaned picture, if it passed the gate
        try:
            cleaned = photo_polish.polished(root, sha)
        except (OSError, media.Refused, editor.UnsafeState):  # the polish store is unusable: today's behaviour
            cleaned = None
    if cleaned is not None:
        data, ext = cleaned, "jpg"
    elif house:
        verdict = _verdict(data)
        if not isinstance(verdict, Refused) and verdict["ok"]:
            data, ext = verdict["jpeg"], "jpg"
        elif not owner_fallback:
            return verdict if isinstance(verdict, Refused) else Retake(verdict["reason"], tuple(verdict["problems"]))
        # Styling is optional. The already decoded, resized, metadata-free owner
        # web copy remains usable even when isolation/style checks fail. Never
        # publish the rejected generated/rendered pixels as the fallback.
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
        if house and not link and have == found[0]:  # flag turned on after the photo went up as it came
            return Refused(ALREADY_RAW)
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
