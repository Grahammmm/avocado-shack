"""HASS-IMAGE-1: a new-item photo cleaned up by OpenAI gpt-image-2 through Hermes, behind the ``photo_polish`` switch.

What it does: when Mike sends a new photo, ``start`` runs in the background (a daemon thread, started after the reply is
queued, so the interview never waits). It asks Hermes to edit the photo into a catalog picture (plain warm ivory
background, even light, centred, true colours), checks that the product is still the same product (``gate``) and settles
ONE decision for the photo in the private media store. ``photos.install`` then publishes the settled picture: the
cleaned one when it passed the gate (placed and scaled to the catalog's square by ``frame``, 800x800 JPEG, no
metadata; nothing is cut out), otherwise exactly what it
published before this card (the house-style render of Mike's own photo, or the retake ask when that cannot be made).
Every failure (no Hermes, timeout after ``TIMEOUT_S``, refusal, wrong size or type, huge file, gate rejection) ends in
that fallback, silently for Mike; a short ``polish-<code>`` row goes to the correspondence log.

The switch: settings ``photo_polish`` (JSON true/false, absent = false). It only has an effect together with
``houseRender`` true (the polished picture replaces the house render); conversation.load_settings refuses it alone.
The model: ``MODEL`` below is the one line to change (``<Hermes image plugin>:<model id>``).

Credentials: Hass never sees, reads or stores a key. The image call runs inside a Hermes process
(``hass/photo_polish_hermes.py`` under the Hermes interpreter) through Hermes' own image plugin and sign-in.

Determinism: ``photos.install`` runs at prepare, apply and verify and must give the same bytes each time. The decision
is written once (never overwritten, ``media._write_new``); if install comes first it settles the fallback itself and a
late answer is dropped (``polish-late``). Storage, all private, outside the repository and the site:
  <mediaRoot>/polish/<sha[:2]>/<sha>.json   {"use": "polished" | "house", "code", "model", "seconds", "jpeg_sha256"}
  <mediaRoot>/polish/<sha[:2]>/<sha>.jpg    the picture to publish, only for "polished"
The original photo stays where media.py keeps it; only the settled JPEG is ever copied into the site.

The fidelity gate (``gate``) needs no model: the edited product, cut from its clean background, must be found again in
Mike's photo (grey-level correlation over position and scale), with the same colour there, and the label words that
tesseract reads must not change either way: no word on the edit that is not in the photo at that spot, no word of the
photo's product missing from the edit. Without a working tesseract read the edit is unverified and never published.
Thresholds were calibrated on real gpt-image-2 edits and deliberate bad outputs (HASS-IMAGE-1 T2/T3).
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from hass import house_style as hs, media, newitem_render

MODEL = "openai-codex:gpt-image-2-high"  # THE model line: <Hermes image plugin>:<model id> (gpt-image-2, quality high)
SETTING = "photo_polish"  # settings key; only the JSON value true turns the polish on (with houseRender true)
TIMEOUT_S = 90  # the whole Hermes call; after this the fallback is used
FOLDER = "polish"
MAX_OUTPUT_BYTES = 25 * 1024 * 1024  # the plugin's own input cap; a bigger answer is refused unread
SIDE = (512, 4096)  # the edited picture's smallest and largest side in px
SQUARE = 0.9  # shorter side / longer side at least this: the cards are square
PROMPT = (
    "Clean up this product photo for a small shop's online catalog. Keep the product exactly as it is: the same single "
    "item or group, the same shape, size proportions, colours, materials, lid or cap, and every letter of the label "
    "exactly as printed. Do not add, remove or change any item, label, text, logo, sticker or packaging, and add no "
    "props, hands, text, watermark, border or price. Only change the setting: place the product, upright and complete, "
    "large and centred, on a smooth seamless warm ivory background (about RGB 245 240 230) with soft even diffuse light "
    "from the upper left and a soft natural contact shadow under it. Remove the room, wall, counter and any clutter. "
    "True, natural colours; no stylising. Square picture.")

MATCH_MIN = 0.55  # grey-level correlation of the edited product with the best place in Mike's photo
HUE_SHIFT_MAX = 30  # degrees the product's mean hue may move (relighting moves it a little; a recolour a lot)
CHROMA_MAX = 0.080  # largest mean chromaticity (r, g share) difference: catches a recolour the mean hue misses
COLOURED = 0.15  # share of the product's pixels that must be clearly coloured for the hue comparison
STRETCH = (0.85, 0.92, 1.0, 1.08, 1.17)  # width stretches tried: a product turned a little looks narrower or wider
TEXT_CONF = 60  # tesseract confidence a word on the edited picture needs to count
TEXT_TOKEN = re.compile(r"[A-Z0-9]{3,}")
WORD_MIN = 0.35  # each label word on the edited picture must correlate this well with the same spot of Mike's photo
WORD_SURE = 0.45  # ...and a 4+ letter word under this must also be among the words read on Mike's photo (if any read)
KNOWN_RATIO = 0.6  # difflib similarity that counts as the same word read twice (OCR slips: HONE!/HONEY, ROAS/ROAST)
WORD_PX = 8  # a word under this many px high in Mike's photo is too small to judge
WORD_HEIGHT = 24  # both word patches are compared at this height
WORD_SEARCH = 0.6  # the search around the mapped spot, as a share of the word's size
WORD_ZOOM = (0.85, 1.0, 1.15)  # word sizes tried around the mapped one
WORK = 200  # Mike's photo is searched on a copy this many px on its long side
ALLOWED_STYLE = {"no photo background left inside the product (patterned cloth, planks)"}  # a white label panel on a
# generated seamless background is not left-over photo background; every other house-style hard failure rejects

_running: set = set()
_lock = threading.Lock()


def enabled(settings) -> bool:
    return settings.get(SETTING) is True and settings.get("houseRender") is True


# ---------------------------------------------------------------- the Hermes transport
class HermesTransport:
    """``transport(src, out, timeout) -> {"ok": bool, "code": str}``: one Hermes image EDIT of ``src`` written to
    ``out``. The Hermes interpreter and source root are read from the installed ``hermes`` launcher script."""

    def __init__(self, model=MODEL, python=None, root=None, launcher=None):
        self.model, self.python, self.root, self.launcher = model, python, root, launcher

    def _locate(self):
        if not (self.python and self.root):
            found = find_hermes(self.launcher or shutil.which("hermes"))
            if found is None:
                return None, None
            self.python, self.root = found
        return self.python, self.root

    def __call__(self, src, out, timeout=TIMEOUT_S):
        python, root = self._locate()
        if python is None or root is None:
            return {"ok": False, "code": "no-hermes"}
        runner = Path(__file__).with_name("photo_polish_hermes.py")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", dir=Path(out).parent, delete=False, encoding="utf-8") as fh:
            fh.write(PROMPT)
        try:
            done = subprocess.run([python, str(runner), root, self.model, str(src), str(out), fh.name],
                                  capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"ok": False, "code": "timeout"}
        except OSError:
            return {"ok": False, "code": "no-hermes"}
        finally:
            os.unlink(fh.name)
        try:
            said = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"ok": False, "code": "hermes"}
        if not isinstance(said, dict) or said.get("ok") is not True:
            code = said.get("code") if isinstance(said, dict) else None
            return {"ok": False, "code": code if isinstance(code, str) and re.fullmatch(r"[a-z-]{1,20}", code) else "failed"}
        return {"ok": True, "code": "ok"}


_EXEC_RE = re.compile(r"exec (/\S*/python3[\w.]*) ")
_ROOT_RE = re.compile(r"sys\.path\.insert\(0, '\"'\"'(/[^'\"]+)'\"'\"'\)")
_RELEASE_RE = re.compile(r"release_root=\$\(readlink -f (/\S+)\)")


def find_hermes(launcher, _hops=2):
    """(python, root) of the Hermes install behind a ``hermes`` launcher script, or None. Reads launcher text only."""
    try:
        text = Path(launcher).read_text("utf-8")[:20000] if launcher else ""
    except (OSError, UnicodeDecodeError):
        return None
    py, root = _EXEC_RE.search(text), _ROOT_RE.search(text)
    if py and root and Path(py[1]).is_file() and Path(root[1]).is_dir():
        return py[1], root[1]
    release = _RELEASE_RE.search(text)
    if release and _hops:
        return find_hermes(str(Path(release[1]).resolve() / ".hermes" / "bin" / "hermes"), _hops - 1)
    return None


# ---------------------------------------------------------------- the decision store
def _folder(root, sha) -> Path:
    base = media._open_root(root)
    media._private_dir(base / FOLDER)
    folder = base / FOLDER / sha[:2]
    media._private_dir(folder)
    return folder


def decision(root, sha):
    """The settled decision dict for a stored photo, or None when nothing is settled yet."""
    raw = media._existing(_folder(root, sha) / f"{sha}.json")
    if raw is None:
        return None
    try:
        got = json.loads(raw) if len(raw) <= media.SIDECAR_MAX else None
    except ValueError:
        got = None
    return got if isinstance(got, dict) and got.get("use") in ("polished", "house") else {"use": "house", "code": "bad-record"}


def _settle(root, sha, use, code, *, jpeg=None, seconds=None) -> bool:
    """Write the decision once. False when one was already there (a later answer never replaces it)."""
    folder = _folder(root, sha)
    record = {"use": use, "code": code, "model": MODEL, "seconds": seconds,
              "jpeg_sha256": hashlib.sha256(jpeg).hexdigest() if jpeg else None}
    if media._existing(folder / f"{sha}.json") is not None:
        return False
    if jpeg is not None and media._existing(folder / f"{sha}.jpg") is None:
        media._write_new(folder / f"{sha}.jpg", jpeg)
    try:
        media._write_new(folder / f"{sha}.json", json.dumps(record, sort_keys=True).encode("utf-8") + b"\n")
    except media.Refused:  # the other side settled between the check and the link
        return False
    return True


def polished(root, sha):
    """The cleaned picture ``photos.install`` publishes for this photo, or None for the fallback. Settles the fallback
    when nothing is settled yet, so prepare, apply and verify always agree."""
    got = decision(root, sha)
    if got is None:
        _settle(root, sha, "house", "late" if sha in _running else "not-run")
        got = decision(root, sha)
    if got and got.get("use") == "polished":
        jpeg = media._existing(_folder(root, sha) / f"{sha}.jpg")
        if jpeg is not None and hashlib.sha256(jpeg).hexdigest() == got.get("jpeg_sha256"):
            return jpeg
    return None


# ---------------------------------------------------------------- the run
def start(root, sha, *, log=None, transport=None, timeout=TIMEOUT_S):
    """Polish one stored photo in a daemon thread; the thread, or None when it is settled or running already.
    Never raises and never waits."""
    try:
        if not isinstance(sha, str) or not media.SHA_RE.fullmatch(sha) or decision(root, sha) is not None:
            return None
        media.web_copy(root, sha)  # made here, in the caller's thread: install never races the worker writing it
        with _lock:
            if sha in _running:
                return None
            _running.add(sha)
        worker = threading.Thread(target=run, args=(root, sha), kwargs={"log": log, "transport": transport, "timeout": timeout},
                                  daemon=True, name=f"polish-{sha[:8]}")
        worker.start()
        return worker
    except Exception:  # noqa: BLE001 - a store problem means no polish, never a failed reply
        with _lock:
            _running.discard(sha)
        return None


def run(root, sha, *, log=None, transport=None, timeout=TIMEOUT_S) -> str:
    """The whole step for one photo, in the caller's thread; returns the code settled (or "late")."""
    began = time.monotonic()
    with _lock:
        _running.add(sha)
    try:
        code, jpeg = _attempt(root, sha, transport or HermesTransport(), timeout)
        if not _settle(root, sha, "polished" if jpeg else "house", code, jpeg=jpeg,
                       seconds=round(time.monotonic() - began, 1)):
            code = "late"
    except Exception:  # noqa: BLE001 - never crash the worker; install falls back on its own
        code = "error"
    finally:
        with _lock:
            _running.discard(sha)
    if code != "ok" and log is not None:
        log.record("error", f"polish-{code}", seconds=round(time.monotonic() - began, 1))
    return code


def _attempt(root, sha, transport, timeout):
    """(code, picture to publish or None)."""
    web = media.web_copy(root, sha)
    original = Path(web["path"]).read_bytes()
    with tempfile.TemporaryDirectory(prefix="work-", dir=_folder(root, sha).parent) as work:
        out = Path(work) / "out.img"
        try:
            said = transport(Path(web["path"]), out, timeout)
        except Exception:  # noqa: BLE001
            return "transport", None
        if not isinstance(said, dict) or said.get("ok") is not True:
            code = said.get("code") if isinstance(said, dict) else None
            return (code if isinstance(code, str) and re.fullmatch(r"[a-z-]{1,20}", code) else "failed"), None
        try:
            st = os.lstat(out)
            if not stat.S_ISREG(st.st_mode) or st.st_size == 0:
                return "empty", None
            if st.st_size > MAX_OUTPUT_BYTES:
                return "huge", None
            edited = out.read_bytes()
        except OSError:
            return "empty", None
    result = gate(original, edited)
    return ("ok", result["jpeg"]) if result["ok"] else (result["code"], None)


# ---------------------------------------------------------------- the fidelity gate
def gate(original, edited) -> dict:
    """Is ``edited`` the same product as Mike's photo ``original``? {"ok", "code", "jpeg" (the edited picture as the
    catalog square, ``frame``), "metrics"}. The label is read with tesseract on both pictures: every word the edit
    shows must be in the photo at that spot (``text_changed``) and every word the photo shows on the product must still
    be in the edit at that spot (``text_removed``). When either picture cannot be read (no tesseract, it fails or times
    out) the edit is not verified and is rejected (code ``ocr``): the fallback is published. Every measure is taken
    before deciding, so a rejection still reports all of them."""
    fail = lambda code, **m: {"ok": False, "code": code, "jpeg": None, "metrics": m}  # noqa: E731
    if len(edited) > MAX_OUTPUT_BYTES:
        return fail("huge")
    if media.sniff(edited) is None:
        return fail("type")
    try:
        im = newitem_render._decode(edited)
        short, long_ = sorted(im.size)
        if short < SIDE[0] or long_ > SIDE[1] or short / long_ < SQUARE:
            return fail("size", size=f"{im.width}x{im.height}")
        made = frame(edited)
    except (media.Refused, newitem_render.Refused):
        return fail("type")
    hard = set(made["check"].get("hard_failures") or ())
    if hard - ALLOWED_STYLE or (not hard and not made["check"]["pass"]):
        return fail("style", hard=sorted(hard), score=made["check"].get("score"))
    m = match(original, made["jpeg"])
    if m is None:
        return fail("match")
    mapping = m.pop("_map")
    found = words(made["jpeg"])  # the label as the edit shows it
    read = photo_words(original)  # the label as Mike's photo shows it
    if found is None or read is None:  # the label cannot be checked: never publish an unverified edit
        m["ocr"] = "unavailable"
    else:
        m["words"] = word_scores(original, made["jpeg"], mapping, found)
        m["photo_words"] = sorted({w for w, _box in read})
        m["kept"] = kept_scores(original, made["jpeg"], mapping, read)
        m["text_changed"] = text_changed(m["words"], set(m["photo_words"]))
        m["text_removed"] = text_removed(m["kept"], {w for w, _box in found})
    colour_off = (m["hue_shift"] is not None and m["hue_shift"] > HUE_SHIFT_MAX) or m["chroma"] > CHROMA_MAX
    code = ("match" if m["match"] < MATCH_MIN else "colour" if colour_off else "ocr" if m.get("ocr")
            else "text" if m["text_changed"] or m["text_removed"] else "ok")
    if code != "ok":
        return fail(code, **m)
    return {"ok": True, "code": "ok", "jpeg": made["jpeg"], "metrics": m}


def frame(edited, spec=None) -> dict:
    """{"jpeg", "check"}: the edited picture as a catalog square. The model already put the product on a plain ivory
    background, so nothing is cut out (the house cutout drops label print that sits on cream paper next to the edge):
    the picture is moved and scaled so the product fills the frame like the catalog's (``fill_max`` median, at most
    0.9), the space opened at the sides takes the picture's own border colour, and it is saved as an 800 x 800 JPEG
    with no metadata, at the house render's qualities. Raises newitem_render.Refused for an unreadable picture."""
    Image, ImageChops, _ = _pil()
    spec = spec or hs.load_spec()
    stats = spec["pictures"]["catalog"]["metrics"]
    im = newitem_render._upright(edited)[0]
    w, h = im.size
    ring = [im.getpixel((x, y)) for x in range(0, w, max(1, w // 64)) for y in (2, h - 3)]
    ring += [im.getpixel((x, y)) for y in range(0, h, max(1, h // 64)) for x in (2, w - 3)]
    bg = tuple(sorted(c[i] for c in ring)[len(ring) // 2] for i in range(3))
    small = im.resize((200, max(1, round(200 * h / w))), Image.Resampling.BOX)
    diff = ImageChops.difference(small, Image.new("RGB", small.size, bg)).split()
    box = ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]), diff[2]).point(lambda v: 255 if v > 30 else 0).getbbox()
    if box is None:
        raise newitem_render.Refused("blank")
    k = w / 200
    x0, y0, x1, y1 = (v * k for v in box)
    side = max(x1 - x0, y1 - y0) / min(stats["fill_max"]["p50"], .90)
    canvas = Image.new("RGB", (round(side), round(side)), bg)
    canvas.paste(im, (round(side / 2 - (x0 + x1) / 2), round(side / 2 - (y0 + y1) / 2)))
    canvas = canvas.resize((newitem_render.SIZE, newitem_render.SIZE), Image.Resampling.LANCZOS)
    jpeg = b""
    for quality in newitem_render.JPEG_QUALITIES:  # the house render's rule: the first not heavier than the catalog's
        buf = io.BytesIO()
        canvas.save(buf, "JPEG", quality=quality, optimize=True, subsampling=2)
        jpeg = buf.getvalue()
        if len(jpeg) <= stats["bytes"]["p95"] * 1.3:
            break
    return {"jpeg": jpeg, "check": hs.check_image(jpeg, spec)}


def _pil():
    from PIL import Image, ImageChops, ImageStat  # noqa: PLC0415 - Pillow is optional for Hass, required for pictures
    return Image, ImageChops, ImageStat


def _product(jpeg):
    """(RGB crop, L mask, box) of the product on a framed picture, at 400 px; (None, None, None) without a product.
    The mask is the house render's own cutout (``newitem_render.isolate``: the soft contact shadow is not product), or
    what differs from the corner colour when the cutout finds nothing. It only chooses which pixels are compared; the
    published picture is never cut."""
    Image, ImageChops, _ = _pil()
    full = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im = full.resize((400, 400), Image.Resampling.BOX)
    cut, _report = newitem_render.isolate(full)
    if cut is not None:
        mask = cut.resize((400, 400), Image.Resampling.BOX).point(lambda v: 255 if v > 127 else 0)
    else:
        diff = ImageChops.difference(im, Image.new("RGB", im.size, im.getpixel((4, 4)))).split()
        mask = ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]), diff[2]).point(lambda v: 255 if v > 30 else 0)
    box = mask.getbbox()
    return (None, None, None) if box is None else (im.crop(box), mask.crop(box), box)


def _ncc(ImageChops, ImageStat, crop, tmpl, mask, t_stat):
    """Masked normalised cross-correlation of two L images. The covariance comes from the variance of their mean
    (var((c+t)/2) = (var c + var t + 2 cov) / 4): Pillow has no exact product, and ImageChops.multiply truncates."""
    c = ImageStat.Stat(crop, mask)
    if c.stddev[0] < 2 or t_stat.stddev[0] < 2:  # a flat patch matches nothing
        return -1.0
    both = ImageStat.Stat(ImageChops.add(crop, tmpl, 2.0), mask).var[0]
    cov = (4 * both - c.var[0] - t_stat.var[0]) / 2
    return cov / (c.stddev[0] * t_stat.stddev[0])


def _template(Image, grey, mask, tw, th):
    t = grey.resize((tw, th), Image.Resampling.BOX)
    m = mask.resize((tw, th), Image.Resampling.BOX).point(lambda v: 255 if v > 127 else 0)
    return t, m


def _channels(rgb):
    """The images the product is matched on: grey, plus colour saturation (steadier than brightness when the light
    changes, e.g. amber honey or a blue box under new light)."""
    return [rgb.convert("L"), rgb.convert("HSV").getchannel("S")]


def match(original, framed):
    """Find the edited product (cut from the house-framed ``framed``) in Mike's photo: the best mean correlation of grey
    and saturation over position, size and stretch (a product turned a little looks narrower or wider), then the colour
    of Mike's photo there against the edited product (mean hue shift; mean chromaticity when it has no clear hue).
    None without a product."""
    Image, ImageChops, ImageStat = _pil()
    rgb, mask, box = _product(framed)
    if rgb is None:
        return None
    photo, _alpha, _turned = newitem_render._upright(original)
    full = photo.size
    photo = photo.copy()
    photo.thumbnail((WORK, WORK), Image.Resampling.BOX)
    (w, h) = photo.size
    chans, tchans = _channels(photo), _channels(rgb)
    if ImageStat.Stat(tchans[1], mask).stddev[0] < 8:  # a colourless product: grey only
        chans, tchans = chans[:1], tchans[:1]

    def score(x, y, tms, tss):
        return sum(_ncc(ImageChops, ImageStat, c.crop((x, y, x + tms[0][0].width, y + tms[0][0].height)), t, m, s)
                   for c, (t, m), s in zip(chans, tms, tss)) / len(chans)

    def templates(tw, th):
        tms = [_template(Image, c, mask, tw, th) for c in tchans]
        return tms, [ImageStat.Stat(t, m) for t, m in tms]
    best = (-2.0, None)
    for i in range(16):
        size = round(min(w, h) * 0.22 * 1.11 ** i)
        for stretch in STRETCH:
            tw = round(size * rgb.width / max(rgb.size) * stretch)
            th = round(size * rgb.height / max(rgb.size))
            if not (8 <= tw <= w and 8 <= th <= h):
                continue
            tms, tss = templates(tw, th)
            step = max(2, min(tw, th) // 8)
            for y in range(0, h - th + 1, step):
                for x in range(0, w - tw + 1, step):
                    s = score(x, y, tms, tss)
                    if s > best[0]:
                        best = (s, (x, y, tw, th, step))
    if best[1] is None:
        return None
    x0, y0, tw, th, step = best[1]
    tms, tss = templates(tw, th)
    for y in range(max(0, y0 - step), min(h - th, y0 + step) + 1):  # refine around the coarse best, one px at a time
        for x in range(max(0, x0 - step), min(w - tw, x0 + step) + 1):
            s = score(x, y, tms, tss)
            if s > best[0]:
                best = (s, (x, y, tw, th, step))
    x, y, tw, th, _ = best[1]
    m = tms[0][1]
    here, there = photo.crop((x, y, x + tw, y + th)), rgb.resize((tw, th), Image.Resampling.BOX)
    chroma = lambda c: (c[0] / max(1, sum(c)), c[1] / max(1, sum(c)))  # noqa: E731
    a, b = chroma(ImageStat.Stat(here, m).mean), chroma(ImageStat.Stat(there, m).mean)
    ha, hb = _hue(here, m), _hue(there, m)
    shift = round(min(abs(ha - hb), 360 - abs(ha - hb)), 1) if ha is not None and hb is not None else None
    return {"match": round(best[0], 3), "hue_shift": shift, "chroma": round(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 4),
            "where": [round(x / w, 3), round(y / h, 3), round(tw / w, 3), round(th / h, 3)],
            "_map": (full, (x / w, y / h, tw / w, th / h), tuple(v * 2 for v in box))}  # framed 800 px -> photo px


def _hue(rgb, mask):
    """Saturation-weighted circular mean hue (degrees) of the clearly coloured pixels under mask, or None when fewer than
    COLOURED of the pixels are clearly coloured (a white, grey or black product has no hue to keep)."""
    sx = sy = weight = 0.0
    total = found = 0
    for (hh, s, v), keep in zip(rgb.convert("HSV").getdata(), mask.getdata()):
        if not keep:
            continue
        total += 1
        if s >= 70 and v >= 50:
            found += 1
            angle = hh * 2 * math.pi / 256
            sx, sy, weight = sx + s * math.cos(angle), sy + s * math.sin(angle), weight + s
    if not total or found < COLOURED * total or math.hypot(sx, sy) < 0.2 * weight:  # no dominant hue
        return None
    return math.degrees(math.atan2(sy, sx)) % 360


def words(framed, scale=2):
    """[(word, (left, top, width, height))] for the label words tesseract reads on the house-framed 800 px edited picture
    (read at ``scale`` times the size, where small label print is still legible; boxes in the picture's own coordinates;
    capital letters and digits, 3+ long, at least TEXT_CONF sure), or None without tesseract."""
    exe = shutil.which("tesseract")
    if exe is None:
        return None
    Image, _, _ = _pil()
    big = Image.open(io.BytesIO(framed)).convert("L")
    big = big.resize((big.width * scale, big.height * scale), Image.Resampling.LANCZOS)
    with tempfile.NamedTemporaryFile(suffix=".png") as fh:
        big.save(fh, "PNG")
        fh.flush()
        try:
            done = subprocess.run([exe, fh.name, "-", "--psm", "11", "tsv"], capture_output=True, text=True, timeout=30,
                                  check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if done.returncode != 0 or not done.stdout.startswith("level\t"):  # a failed read is no read, not an empty label
        return None
    out = []
    for line in done.stdout.splitlines()[1:]:
        cols = line.split("\t")
        try:
            conf, box = float(cols[10]), tuple(int(v) // scale for v in cols[6:10])
        except (IndexError, ValueError):
            continue
        token = "".join(TEXT_TOKEN.findall(cols[11].upper()))
        if conf >= TEXT_CONF and len(token) >= 3:
            out.append((token, box))
    return out


def word_scores(original, framed, mapping, found):
    """For each word read on the edited picture: how well the same spot of Mike's photo shows the same marks (the best
    grey correlation within a small search around where ``match`` maps it), or None when it is too small there to
    judge. A changed, added or invented word does not look like what is in the photo at that spot."""
    Image, _, _ = _pil()
    (fw, fh), (rx, ry, rw, rh), (bx0, by0, bx1, by1) = mapping
    photo = newitem_render._upright(original)[0].convert("L")
    grey = Image.open(io.BytesIO(framed)).convert("L")
    sx, sy = rw * fw / max(1, bx1 - bx0), rh * fh / max(1, by1 - by0)  # photo px per framed px
    out = []
    for word, (left, top, width, height) in found:
        at = (rx * fw + (left - bx0) * sx, ry * fh + (top - by0) * sy)  # the word's top-left in Mike's photo
        out.append((word, _spot(grey, (left, top, width, height), photo, at, (sx, sy))))
    return out


def kept_scores(original, framed, mapping, read):
    """The other way round: for each word read on Mike's photo, how well the same spot of the edited picture shows
    the same marks, or None when that cannot be judged (it is off the place ``match`` found the product, too small, or
    has no marks). A blanked or partly erased label does not look like the photo's words there any more. The search
    reaches no further sideways than up and down: a wide one would let an erased word match the next word along."""
    Image, _, _ = _pil()
    (fw, fh), (rx, ry, rw, rh), (bx0, by0, bx1, by1) = mapping
    photo = newitem_render._upright(original)[0].convert("L")
    grey = Image.open(io.BytesIO(framed)).convert("L")
    sx, sy = rw * fw / max(1, bx1 - bx0), rh * fh / max(1, by1 - by0)  # photo px per framed px
    out = []
    for word, (left, top, width, height) in read:
        mid_x, mid_y = left + width / 2, top + height / 2
        if not (rx * fw <= mid_x <= (rx + rw) * fw and ry * fh <= mid_y <= (ry + rh) * fh):
            out.append((word, None))
            continue
        at = (bx0 + (left - rx * fw) / sx, by0 + (top - ry * fh) / sy)  # the word's top-left on the edited picture
        out.append((word, _spot(photo, (left, top, width, height), grey, at, (1 / sx, 1 / sy),
                                slide=WORD_SEARCH * height / max(1, width))))
    return out


def _spot(src, box, dst, at, step, *, slide=WORD_SEARCH):
    """The best grey correlation of the word ``box`` (left, top, width, height) of ``src`` with ``dst`` in a small
    search around ``at`` (the word's mapped top-left in ``dst`` px; ``step``: dst px per src px), both brought to a word
    WORD_HEIGHT px high; None when the word is under WORD_PX high on either picture or has no marks to compare. The
    search reaches WORD_SEARCH of the word's height up and down and ``slide`` of its width sideways."""
    Image, ImageChops, ImageStat = _pil()
    left, top, width, height = box
    (cx, cy), (sx, sy) = at, step
    if min(height, height * sy) < WORD_PX:
        return None
    k = WORD_HEIGHT / height
    tmpl = src.crop((left, top, left + width, top + height))
    tmpl = tmpl.resize((max(4, round(width * k)), WORD_HEIGHT), Image.Resampling.LANCZOS)
    if ImageStat.Stat(tmpl).stddev[0] < 2:  # no marks in the box: nothing to compare
        return None
    pad_x, pad_y = width * sx * slide, height * sy * WORD_SEARCH
    area = (round(cx - pad_x), round(cy - pad_y), round(cx + width * sx + pad_x), round(cy + height * sy + pad_y))
    full = Image.new("L", tmpl.size, 255)
    ts = ImageStat.Stat(tmpl, full)
    best = -1.0
    for zoom in WORD_ZOOM:  # the mapping is only as exact as the match's size steps: try a little bigger and smaller
        region = dst.crop(area).resize((max(1, round((area[2] - area[0]) * k * zoom / sx)),
                                        max(1, round((area[3] - area[1]) * k * zoom / sy))), Image.Resampling.LANCZOS)
        for y in range(0, max(1, region.height - tmpl.height + 1)):
            for x in range(0, max(1, region.width - tmpl.width + 1), 2):
                best = max(best, _ncc(ImageChops, ImageStat, region.crop((x, y, x + tmpl.width, y + tmpl.height)),
                                      tmpl, full, ts))
    return round(best, 3)


def photo_words(original):
    """[(word, (left, top, width, height))] for the label words tesseract reads on Mike's photo itself (same rules as
    ``words``, read at up to 1600 px; boxes in the upright photo's own px), or None when it cannot be read."""
    try:
        photo = newitem_render._upright(original)[0].convert("RGB")
    except (media.Refused, newitem_render.Refused):
        return None
    full = photo.width
    photo.thumbnail((1600, 1600))  # a phone photo's full size only slows tesseract down
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=92)
    found = words(buf.getvalue(), scale=1)
    if found is None:
        return None
    k = full / photo.width
    return [(w, tuple(round(v * k) for v in box)) for w, box in found]


def _known(word, known) -> bool:
    """Is ``word`` (read on the edited picture) one of the words read on Mike's photo, allowing for OCR slips?"""
    return any(word in k or k in word or difflib.SequenceMatcher(None, word, k).ratio() >= KNOWN_RATIO
               for k in known if len(k) >= 3)


def text_changed(scores, known=None) -> bool:
    """True when a word the edited label shows is not in Mike's photo at that spot (judgeable words only): it looks
    unlike that spot, or it only looks a little like it (under WORD_SURE) and is not among the words read on the photo
    (when the photo reads at all). A plausible but different word in the same place is the case the second rule
    catches."""
    for word, s in scores:
        if s is None:
            continue
        if s < WORD_MIN:
            return True
        if known and s < WORD_SURE and len(word) >= 4 and not _known(word, known):
            return True
    return False


def text_removed(kept, edit_words) -> bool:
    """True when a word Mike's photo shows is gone from the edit. A word read on the edit too is kept. Otherwise it
    must still look like that spot of the edited picture: not under WORD_MIN (flat paper there scores -1), and a 4+
    letter word not under WORD_SURE (a blanked label still has faint patch edges). A 4+ letter word that cannot be
    judged there (off the place ``match`` found, or too small) and is not read on the edit counts as gone: preservation
    is not established, so the fallback is used (a word on the room behind the product costs only the polish)."""
    for word, s in kept:
        if len(word) < 3 or _known(word, edit_words):
            continue
        if s is None:
            if len(word) >= 4:
                return True
        elif s < WORD_MIN or (s < WORD_SURE and len(word) >= 4):
            return True
    return False
