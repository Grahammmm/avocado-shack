"""HASS-NEWITEM-1: synthetic product photos for the new-item prototype and its tests. Pillow only; nothing is a real photo.

make_photo(...) draws a jar, bottle or bag on a chosen background at a chosen size and angle, optionally saved the way
a phone stores it: sideways pixels plus an EXIF Orientation tag, with made-up device, time and GPS values so a test can
prove the render drops them. Drawing is deterministic (seeded noise), so the same arguments give the same bytes.
"""
from __future__ import annotations

import io
import random

from hass import house_style as hs

BACKGROUNDS = ("white-sheet", "grey-wall", "kitchen-bench", "dark-wood", "red-cloth")
PRODUCTS = ("jar", "bottle", "bag")
PLAIN = ("white-sheet", "grey-wall", "kitchen-bench")  # the ones deterministic isolation is expected to separate


def _background(Image, ImageDraw, size, kind, rng):
    w, h = size
    if kind == "white-sheet":
        base, tilt = (236, 236, 232), (10, 8, 6)
    elif kind == "grey-wall":
        base, tilt = (150, 154, 158), (-22, -20, -18)
    elif kind == "kitchen-bench":
        base, tilt = (205, 190, 165), (8, 6, 2)
    elif kind == "dark-wood":
        base, tilt = (70, 46, 30), (0, 0, 0)
    else:
        base, tilt = (170, 40, 40), (0, 0, 0)
    img = Image.new("RGB", size, base)
    d = ImageDraw.Draw(img)
    for y in range(h):  # a smooth top-to-bottom light fall-off
        f = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(max(0, min(255, round(base[i] + tilt[i] * f))) for i in range(3)))
    if kind == "dark-wood":
        for i in range(0, w, max(6, w // 90)):
            d.rectangle((i, 0, i + max(3, w // 160), h), fill=(max(0, base[0] + rng.randint(-45, 60)), max(0, base[1] + rng.randint(-35, 45)), max(0, base[2] + rng.randint(-20, 30))))
    if kind == "red-cloth":
        step = max(12, w // 14)
        for gx in range(0, w, step):
            for gy in range(0, h, step):
                if (gx // step + gy // step) % 2:
                    d.rectangle((gx, gy, gx + step, gy + step), fill=(235, 235, 235))
    for _ in range(w * h // 900):  # light speckle: sensor noise / bench grain
        x, y, v = rng.randrange(w), rng.randrange(h), rng.randint(-5, 5)
        px = img.getpixel((x, y))
        img.putpixel((x, y), tuple(max(0, min(255, c + v)) for c in px))
    return img


def _product(Image, ImageDraw, ImageFont, kind, height):
    """RGBA drawing of one product, `height` px tall, transparent around it."""
    if kind == "jar":
        w = round(height * .72)
        layer = Image.new("RGBA", (w, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((0, round(height * .14), w - 1, height - 1), radius=round(w * .14), fill=(214, 140, 28, 255), outline=(150, 92, 12, 255), width=3)
        d.rounded_rectangle((round(w * .08), 0, round(w * .92), round(height * .17)), radius=round(w * .05), fill=(40, 40, 44, 255))
        d.rectangle((round(w * .12), round(height * .38), round(w * .88), round(height * .74)), fill=(246, 238, 214, 255), outline=(120, 100, 60, 255))
        text = "HONEY"
    elif kind == "bottle":
        w = round(height * .3)
        layer = Image.new("RGBA", (w, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((0, round(height * .3), w - 1, height - 1), radius=round(w * .25), fill=(40, 120, 52, 255), outline=(20, 70, 30, 255), width=3)
        d.rectangle((round(w * .3), round(height * .08), round(w * .7), round(height * .32)), fill=(40, 120, 52, 255))
        d.rectangle((round(w * .26), 0, round(w * .74), round(height * .1)), fill=(200, 40, 30, 255))
        d.rectangle((round(w * .08), round(height * .5), round(w * .92), round(height * .8)), fill=(250, 244, 226, 255))
        text = "SAUCE"
    else:
        w = round(height * .62)
        layer = Image.new("RGBA", (w, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((0, 0, w - 1, height - 1), radius=round(w * .06), fill=(122, 84, 52, 255), outline=(80, 52, 30, 255), width=3)
        d.rectangle((round(w * .1), round(height * .3), round(w * .9), round(height * .7)), fill=(244, 236, 214, 255))
        text = "COFFEE"
    font = ImageFont.load_default()
    d.text((round(w * .5) - 3 * len(text), round(height * .52)), text, fill=(60, 40, 20, 255), font=font)
    return layer


def make_photo(product="jar", background="white-sheet", size=(1200, 900), angle=0, share=.62, seed=1, phone_orientation=None,
               fmt="JPEG", alpha=False) -> bytes:
    """Photo bytes. `share` is the product's height as a share of the picture; `angle` tilts it in degrees;
    `phone_orientation` (6 or 8) stores the picture sideways with that EXIF tag, as a phone does, plus fake GPS/device data."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: PLC0415
    rng = random.Random(seed)
    upright = (size[1], size[0]) if phone_orientation else size  # the scene as seen; stored sideways later
    w, h = upright
    scene = _background(Image, ImageDraw, upright, background, rng) if not alpha else Image.new("RGBA", upright, (0, 0, 0, 0))
    item = _product(Image, ImageDraw, ImageFont, product, round(h * share))
    if angle: item = item.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    left, top = (w - item.width) // 2 + rng.randint(-w // 40, w // 40), (h - item.height) // 2 + rng.randint(-h // 60, h // 60)
    if not alpha:  # a soft shadow on the surface, as a real photo has
        shadow = Image.new("L", upright, 0)
        ImageDraw.Draw(shadow).ellipse((left, top + item.height - item.height // 14, left + item.width, top + item.height + item.height // 14), fill=90)
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(3, h // 70)))
        scene = Image.composite(Image.new("RGB", upright, (40, 40, 40)), scene, shadow)
    scene.paste(item, (left, top), item)
    stored = scene
    exif = None
    if phone_orientation:
        stored = scene.transpose(Image.Transpose.ROTATE_90 if phone_orientation == 6 else Image.Transpose.ROTATE_270)  # sideways pixels
        exif = Image.Exif()
        exif[0x010F], exif[0x0110], exif[0x0132], exif[0x0112] = "SyntheticCo", "Phone 0", "2026:11:07 09:30:00", phone_orientation
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2], gps[3], gps[4] = "N", (35.0, 22.0, 0.0), "W", (120.0, 51.0, 0.0)
    out = io.BytesIO()
    if fmt == "PNG":
        stored.save(out, "PNG", **({"exif": exif} if exif is not None else {}))
    else:
        stored.convert("RGB").save(out, "JPEG", quality=84, **({"exif": exif} if exif is not None else {}))
    return out.getvalue()


def has_exif_location(data: bytes) -> bool:
    from PIL import Image  # noqa: PLC0415
    ex = Image.open(io.BytesIO(data)).getexif()
    return bool(ex.get_ifd(0x8825)) or any(k in ex for k in (0x010F, 0x0110, 0x0132))


def cases() -> list:
    """The prototype's synthetic set: (name, kwargs). Plain backgrounds, two angles, three sizes, a phone photo with a
    rotation tag and GPS, a PNG, a transparent cut-out, and two backgrounds that deterministic isolation cannot separate."""
    return [("jar-white-sheet", dict(product="jar", background="white-sheet", size=(1200, 900), seed=1)),
            ("bottle-grey-wall-tilted", dict(product="bottle", background="grey-wall", size=(1000, 1000), angle=12, seed=2)),
            ("bag-bench-small", dict(product="bag", background="kitchen-bench", size=(480, 360), seed=3)),
            ("jar-phone-rotated", dict(product="jar", background="white-sheet", size=(1512, 1134), phone_orientation=6, seed=4)),
            ("bottle-bench-png", dict(product="bottle", background="kitchen-bench", size=(900, 1200), fmt="PNG", seed=5)),
            ("jar-cutout-alpha", dict(product="jar", background="white-sheet", size=(900, 900), alpha=True, fmt="PNG", seed=6)),
            ("jar-dark-wood", dict(product="jar", background="dark-wood", size=(1200, 900), seed=7)),
            ("bag-red-cloth", dict(product="bag", background="red-cloth", size=(1200, 900), seed=8))]
