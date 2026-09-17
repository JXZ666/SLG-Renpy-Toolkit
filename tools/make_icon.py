"""Draw assets/rpykit-luna.ico.

Build-time only, run by hand:

    python -m pip install pillow
    python tools/make_icon.py

Pillow never reaches the exe. Nothing in the frozen app imports PIL, the script
is not in hiddenimports, and it is not in datas  -  so PyInstaller's PIL hook
never fires, because hooks only run for modules the Analysis actually reaches.
The .ico is read by PyInstaller while it writes the PE resources and by nothing
else. Do not import this module from luna_main.py or lunagui.py, or that stops
being true and the exe grows by the whole of Pillow.

The glyph comes from assets/NotoSansSC-VF.ttf, which is already in the tree for
the font shim, so no artwork is checked in.
"""

import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(HERE, os.pardir, "assets"))
OUT = os.path.join(ASSETS, "rpykit-luna.ico")
FONT = os.path.join(ASSETS, "NotoSansSC-VF.ttf")

MASTER = 256
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BG = (18, 44, 86)
MOON = (87, 200, 255)
INK = (255, 255, 255)


def _font(size):
    f = ImageFont.truetype(FONT, size)
    for name in ("Bold", "SemiBold", "Medium"):
        try:
            f.set_variation_by_name(name)
            return f
        except Exception:  # noqa: BLE001 - not every build exposes named instances
            continue
    return f


def _crescent(d, box):
    """A moon: a filled disc with a second disc of the background punched in.

    Drawn as background rather than as a mask because the plate underneath is a
    flat colour, so there is nothing for the punch-out to reveal by accident.
    """
    x0, y0, x1, y1 = box
    d.ellipse(box, fill=MOON)
    r = (x1 - x0) / 2.0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    d.ellipse([cx - r * 0.30, cy - r * 1.30, cx + r * 1.70, cy + r * 0.70], fill=BG)


def master():
    im = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    d.rounded_rectangle([0, 0, MASTER - 1, MASTER - 1],
                        radius=round(MASTER * 0.205), fill=BG)

    # Tucked into the corner, above the character's top-right stroke.
    m = MASTER * 0.27
    _crescent(d, [MASTER - m - MASTER * 0.085, MASTER * 0.085,
                  MASTER - MASTER * 0.085, MASTER * 0.085 + m])

    # Optical centre: a Hanzi reads as sitting low when boxed geometrically, so
    # the anchor goes a little above the middle, and left to clear the moon.
    f = _font(round(MASTER * 0.60))
    d.text((MASTER * 0.445, MASTER * 0.565), "\u9732", font=f, fill=INK, anchor="mm")
    return im


if __name__ == "__main__":
    im = master()
    # Pillow picks the frame format per size itself: BMP for the small ones,
    # PNG for 256. That is the layout Explorer handles best.
    im.save(OUT, format="ICO", sizes=SIZES)

    got = sorted(Image.open(OUT).ico.sizes())
    print("wrote %s" % OUT)
    print("sizes %s" % (got,))
    if got != sorted(SIZES):
        raise SystemExit("expected %s" % (sorted(SIZES),))

    # Handy for eyeballing a tweak without opening the .ico.
    im.resize((256, 256), Image.LANCZOS).save(
        os.path.join(HERE, "_preview.png"))
