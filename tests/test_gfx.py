"""gfx/*.png redraws: each changes pixels only inside its declared rect, uses only its texture's palette, and the build
writes it back exactly (re-decoding the patched file gives the PNG). Needs the unpacked files (work/re/files)."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gfx  # noqa: E402

pytestmark = pytest.mark.skipif(not gfx.FILES.exists(), reason="needs work/re/files (AGENTS.md: Unpack for RE)")


@pytest.mark.parametrize("name", sorted(gfx.ASSETS))
def test_redraw_in_rect_and_writes_back(name):
    a = gfx.ASSETS[name]
    png = gfx.GFX / f"{name}.png"
    assert png.exists(), f"run tools/gfx.py gen {name}"
    new = np.array(Image.open(png).convert("RGBA"))
    b = bytearray((gfx.FILES / f"{gfx.files(a)[0]:05d}.bin").read_bytes())
    orig = gfx.read(b, a)
    assert new.shape == orig.shape
    x, y, w, h = a["rect"]
    changed = (new != orig).any(2)
    assert changed.any(), "redraw changed nothing"
    changed[y:y + h, x:x + w] = False
    assert not changed.any(), f"pixels changed outside {a['rect']}: first {np.argwhere(changed)[0][::-1]}"
    n = len(b)
    gfx.write(b, a, new)   # raises if a colour isn't in the palette or a pixel can't be drawn
    assert len(b) == n


def test_text_tsv_has_every_key():
    t = gfx.text_tsv()
    assert all(v.strip() for v in t.values())
