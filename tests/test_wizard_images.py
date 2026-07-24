"""Offline tests for scripts/make_wizard_images.py (no network, no Winamp)."""
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_wizard_images.py"

MINT = (51, 255, 153)  # #33FF99
TOP = (30, 30, 74)  # #1E1E4A
BOTTOM = (11, 11, 26)  # #0B0B1A


def _generate(tmp_path):
    subprocess.run([sys.executable, str(SCRIPT), "--out-dir", str(tmp_path)],
                   check=True, capture_output=True, text=True)
    return (Image.open(tmp_path / "wizard_large.bmp"),
            Image.open(tmp_path / "wizard_small.bmp"))


def _close_to(pixel, color, tol=8):
    return all(abs(a - b) <= tol for a, b in zip(pixel, color))


def test_wizard_images_have_inno_setup_dimensions(tmp_path):
    large, small = _generate(tmp_path)
    assert large.format == "BMP" and large.size == (164, 314)
    assert small.format == "BMP" and small.size == (55, 55)


def test_wizard_images_use_the_dark_indigo_gradient(tmp_path):
    large, _ = _generate(tmp_path)
    assert _close_to(large.getpixel((82, 1)), TOP)
    assert _close_to(large.getpixel((82, 312)), BOTTOM)


def test_wizard_images_contain_the_mint_logo(tmp_path):
    for img in _generate(tmp_path):
        assert any(_close_to(p, MINT, tol=20) for p in img.getdata())


def test_large_banner_has_the_app_name(tmp_path):
    large, _ = _generate(tmp_path)
    # the "ytm-winamp" caption is near-white text in the bottom band
    band = large.crop((0, 260, 164, 300))
    assert any(min(p) > 200 for p in band.getdata())
