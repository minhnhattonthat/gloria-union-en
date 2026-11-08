"""gfx/*.png redraws: each changes pixels only inside its declared rect, uses only its texture's palette, and the build
writes it back exactly (re-decoding the patched file gives the PNG). Needs the unpacked files (work/re/files)."""
import struct
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
    if new.shape != orig.shape:   # a new canvas: the whole of it is the redraw
        assert a["resize"], f"{name}: size {new.shape[1::-1]} differs from the original {orig.shape[1::-1]}"
    else:
        assert new.shape == orig.shape
        x, y, w, h = a["rect"]
        changed = (new != orig).any(2)
        assert changed.any(), "redraw changed nothing"
        changed[y:y + h, x:x + w] = False
        assert not changed.any(), f"pixels changed outside {a['rect']}: first {np.argwhere(changed)[0][::-1]}"
    n = len(b)
    gfx.write(b, a, new)   # raises if a colour isn't in the palette or a pixel can't be drawn
    assert len(b) == n or a["resize"]
    assert (gfx.read(bytes(b), a)[:new.shape[0], :new.shape[1]] == new).all()
    old = (gfx.FILES / f"{gfx.files(a)[0]:05d}.bin").read_bytes()
    if a["resize"] and old[:4] == b"PTP\0":   # the PTP's other entries moved intact
        cnt = struct.unpack_from("<I", old, 4)[0]
        offs = lambda d: list(struct.unpack_from(f"<{cnt}I", d, 0x10)) + [len(d)]
        o1, o2 = offs(old), offs(bytes(b))
        for i in range(cnt):
            if o1[i] != a["off"]:
                assert old[o1[i]:o1[i + 1]].rstrip(b"\0") == bytes(b[o2[i]:o2[i + 1]]).rstrip(b"\0"), f"entry {i} changed"


def test_text_tsv_has_every_key():
    t = gfx.text_tsv()
    blank = {"cnt_cards", "cnt_people"}   # Japanese counters (枚, 人) English leaves out
    assert all(v.strip() for k, v in t.items() if k not in blank)
    assert all(not t[k] for k in blank)


def test_pack_rects_free_and_capped():
    """draw_pack: the moved words stay in the sheet, overlap neither each other nor a kept rect, and keep the width cap
    (the field bar draws each at a fixed x)."""
    a = gfx.ASSETS["hud_terrain"]
    old = gfx.table_rects(*a["table"])
    new = [[int(x) for x in ln.split()] for ln in (gfx.GFX / "hud_terrain.rects").read_text("utf8").split("\n") if ln]
    moved = set(gfx.WEATHER) | set(range(9, 9 + len(gfx.TERRAIN)))   # a word may land on its old spot
    assert all(o == n for i, (o, n) in enumerate(zip(old, new)) if i not in moved)
    for i in moved:
        u, v, w, h = new[i]
        assert 0 <= u and u + w <= 224 and 0 <= v and v + h <= 202 and h == old[i][3]
        assert w <= (28 if i in gfx.WEATHER else 40) + 1, (i, w)
        for j, (u2, v2, w2, h2) in enumerate(new):
            if j != i and (j in moved or j < 9):
                assert u + w <= u2 or u2 + w2 <= u or v + h <= v2 or v2 + h2 <= v, (i, j)
