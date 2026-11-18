"""HASS-CHAOS-1: draw the synthetic owner photos the chaos cases send (Pillow only, no real product or person).

    python3 hass/tests/chaos/make_photos.py [OUT_DIR]

Writes small JPEGs into hass/tests/chaos/photos/ (or OUT_DIR). Deterministic: the same Pillow version draws the same bytes.
The committed copies are what the recorded tapes were made from; re-running only matters when adding a new photo.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "photos"


def canvas(bg):
    return Image.new("RGB", (640, 640), bg)


def text_block(pen, x, y, lines, fill="#111111"):
    for i, line in enumerate(lines):
        pen.text((x, y + i * 18), line, fill=fill)


def glue():  # a non-food bottle with label wording (the live glue case)
    im = canvas("#d9d4cc")
    pen = ImageDraw.Draw(im)
    pen.rectangle((250, 120, 390, 560), fill="#f4f1ea", outline="#333333", width=4)
    pen.polygon([(290, 120), (350, 120), (330, 60), (310, 60)], fill="#e2a400")
    pen.rectangle((262, 260, 378, 420), fill="#1f1f1f")
    text_block(pen, 270, 280, ["SUPER GRIP", "GLUE", "", "Made in USA", "The strongest glue", "2 fl oz"], fill="#f2c200")
    return im


def jam():  # a food jar whose label carries a claim word
    im = canvas("#efe6da")
    pen = ImageDraw.Draw(im)
    pen.rectangle((200, 220, 440, 540), fill="#7a1230", outline="#3a0a18", width=4)
    pen.rectangle((190, 180, 450, 230), fill="#c9a24a")
    pen.rectangle((230, 320, 410, 450), fill="#fbf6ee")
    text_block(pen, 245, 335, ["HILLSIDE KITCHEN", "Raspberry Jam", "Organic", "Net wt 10 oz"])
    return im


def candle():  # a non-food item described with food words
    im = canvas("#f5f0fa")
    pen = ImageDraw.Draw(im)
    pen.ellipse((210, 500, 430, 560), fill="#bfb3cc")
    pen.rectangle((210, 260, 430, 530), fill="#d8c8ef", outline="#6d5a8a", width=3)
    pen.line((320, 260, 320, 220), fill="#222222", width=4)
    text_block(pen, 245, 360, ["LAVENDER HONEY", "soy candle", "not edible", "8 oz"])
    return im


def persimmons():  # loose produce, no label
    im = canvas("#e9e2cf")
    pen = ImageDraw.Draw(im)
    for x, y in ((140, 250), (330, 300), (230, 410)):
        pen.ellipse((x, y, x + 200, y + 150), fill="#e47522", outline="#a63d0a", width=4)
        pen.polygon([(x + 100, y + 30), (x + 60, y + 8), (x + 92, y + 6), (x + 102, y - 12), (x + 114, y + 7), (x + 146, y + 6), (x + 124, y + 32)], fill="#4a5e2a")
    return im


def blurry():  # the jar again, out of focus: nothing readable
    return jam().filter(ImageFilter.GaussianBlur(14))


def irrelevant():  # a sunset over water: no product at all
    im = canvas("#ffb36b")
    pen = ImageDraw.Draw(im)
    pen.rectangle((0, 400, 640, 640), fill="#2c4f74")
    pen.ellipse((250, 300, 390, 440), fill="#ffd34d")
    for y in range(420, 640, 22):
        pen.line((60, y, 580, y), fill="#3d6690", width=3)
    return im


def back_label():  # the back of the glue bottle: ingredients-like small print
    im = canvas("#d9d4cc")
    pen = ImageDraw.Draw(im)
    pen.rectangle((230, 110, 410, 560), fill="#f4f1ea", outline="#333333", width=4)
    text_block(pen, 240, 160, ["DIRECTIONS:", "Apply to clean", "dry surface.", "", "WARNING: keep away", "from children.", "", "Distributed by", "Grip Co, Ohio"])
    return im


PHOTOS = {"glue.jpg": glue, "jam.jpg": jam, "candle.jpg": candle, "persimmons.jpg": persimmons,
          "blurry.jpg": blurry, "sunset.jpg": irrelevant, "glue-back.jpg": back_label}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in PHOTOS.items():
        draw().save(OUT / name, "JPEG", quality=80)
        print(OUT / name)


if __name__ == "__main__":
    main()
