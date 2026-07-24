"""Generate the Inno Setup wizard images for the ytm-winamp installer.

Draws assets/wizard_large.bmp (164x314 left banner) and
assets/wizard_small.bmp (55x55 header icon) in the app-icon style:
dark indigo gradient, mint play triangle, EQ bars. Re-run after a
rebrand:

    python scripts/make_wizard_images.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOP = (30, 30, 74)  # #1E1E4A
BOTTOM = (11, 11, 26)  # #0B0B1A
MINT = (51, 255, 153)  # #33FF99
TEXT = (235, 235, 245)

LARGE_SIZE = (164, 314)  # Inno Setup WizardImageFile at 100% DPI
SMALL_SIZE = (55, 55)  # Inno Setup WizardSmallImageFile at 100% DPI
SS = 4  # supersampling factor for smooth edges

_FONT_CANDIDATES = ("segoeuib.ttf", "arialbd.ttf", "calibrib.ttf")


def _gradient(size: tuple[int, int]) -> Image.Image:
    """Vertical gradient from TOP (y=0) to BOTTOM."""
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    return img


def _draw_logo(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """Mint play triangle centred at (cx, cy); r = half the triangle height."""
    draw.polygon([(cx - 0.65 * r, cy - r), (cx - 0.65 * r, cy + r), (cx + r, cy)], fill=MINT)


def _draw_eq_bars(draw: ImageDraw.ImageDraw, cx: float, y_top: float, max_h: float,
                  bar_w: float, gap: float) -> None:
    """Four bottom-aligned, round-ended EQ bars centred on cx."""
    total_w = 4 * bar_w + 3 * gap
    x = cx - total_w / 2
    for frac in (0.45, 1.0, 0.35, 0.75):
        draw.rounded_rectangle([x, y_top + max_h * (1 - frac), x + bar_w, y_top + max_h],
                               radius=bar_w / 2, fill=MINT)
        x += bar_w + gap


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:  # PIL searches the Windows fonts dir
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_centered_text(draw: ImageDraw.ImageDraw, cx: float, y: float, text: str,
                        font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bbox[2] - bbox[0]) / 2 - bbox[0], y), text, font=font, fill=TEXT)


def make_large(path: Path) -> None:
    """Left wizard banner: logo up top, app name near the bottom."""
    img = _gradient((LARGE_SIZE[0] * SS, LARGE_SIZE[1] * SS))
    draw = ImageDraw.Draw(img)
    cx = LARGE_SIZE[0] * SS / 2
    _draw_logo(draw, cx, 108 * SS, 32 * SS)
    _draw_eq_bars(draw, cx, 168 * SS, 26 * SS, 10 * SS, 7 * SS)
    _draw_centered_text(draw, cx, 268 * SS, "ytm-winamp", _load_font(19 * SS))
    img.resize(LARGE_SIZE, Image.LANCZOS).save(path, "BMP")


def make_small(path: Path) -> None:
    """Header icon: mini version of the app icon, no text."""
    img = _gradient((SMALL_SIZE[0] * SS, SMALL_SIZE[1] * SS))
    draw = ImageDraw.Draw(img)
    cx = SMALL_SIZE[0] * SS / 2
    _draw_logo(draw, cx, 21 * SS, 12 * SS)
    _draw_eq_bars(draw, cx, 37 * SS, 9 * SS, 3.4 * SS, 2.4 * SS)
    img.resize(SMALL_SIZE, Image.LANCZOS).save(path, "BMP")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("assets"),
                        help="where to write wizard_large.bmp / wizard_small.bmp")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    make_large(args.out_dir / "wizard_large.bmp")
    make_small(args.out_dir / "wizard_small.bmp")
    for name, size in (("wizard_large.bmp", LARGE_SIZE), ("wizard_small.bmp", SMALL_SIZE)):
        print(f"wrote {args.out_dir / name} ({size[0]}x{size[1]})")


if __name__ == "__main__":
    main()
