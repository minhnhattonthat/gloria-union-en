"""PTX scan and PTG@ compositing on synthetic bytes (no dump needed)."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ptx  # noqa: E402


def tex(w, h, pixels, palette=None):
    """Unswizzled CLUT8 PTX@; without a palette it reuses the previous piece's, like the game's split textures."""
    pal = b"".join(palette) if palette else b""
    head = b"PTX@" + struct.pack("<BBHHHBBB", 4, 3, w, w, h, 5, 0, 3) + b"\0" + struct.pack("<I", 2) + b"\0" * 4
    head += struct.pack("<II", 0x20 if palette else 0, 0x20 + len(pal))
    return head + pal + pixels


RED, BLUE = bytes((255, 0, 0, 255)), bytes((0, 0, 255, 255))


def test_encode_roundtrip_and_palette_check():
    """encode(decode(x)) gives the original bytes (CLUT8 and swizzled CLUT4); a colour outside the palette fails."""
    import numpy as np
    import pytest
    b = tex(4, 2, bytes([0, 1, 1, 0, 1, 0, 0, 1]), [RED, BLUE])
    t = ptx.parse(b)
    assert ptx.encode(b, t, ptx.decode(b, t)) == b[t["do"]:]
    img = ptx.decode(b, t).copy()
    img[0, 0] = (0, 255, 0, 255)
    with pytest.raises(ValueError):
        ptx.encode(b, t, img)
    assert ptx.encode(b, t, img, nearest=True)[0] in (0, 1)
    # swizzled CLUT4, 32x8 (16 bytes a row: one block column)
    px = bytes(np.random.default_rng(1).integers(0, 256, 32 * 8 // 2, dtype=np.uint8))
    head = b"PTX@" + struct.pack("<BBHHHBBB", 5, 3, 32, 32, 8, 4, 1, 3) + b"\0" + struct.pack("<I", 16) + b"\0" * 4
    pal = b"".join(bytes((i * 16, 0, 0, 255)) for i in range(16))
    b4 = head + struct.pack("<II", 0x20, 0x60) + pal + px
    t4 = ptx.parse(b4)
    assert ptx.encode(b4, t4, ptx.decode(b4, t4)) == px


def test_second_piece_shares_the_palette():
    b = tex(4, 2, bytes(8), [RED, BLUE]) + tex(4, 2, bytes([1]) * 8)
    a, c = ptx.scan(b)
    assert c["po"] == a["po"]
    assert tuple(ptx.decode(b, c)[0, 0]) == (0, 0, 255, 255)


def test_ptg_stacks_pieces_and_places_quads():
    block = tex(4, 2, bytes(8), [RED, BLUE]) + tex(4, 2, bytes([1]) * 8)
    # quad 1: piece 0 (1,1)-(3,2) at (2,0); quad 2: piece 1 (0,0)-(2,1) at (2,1); +0x14 counts: 1 quad per piece
    verts = struct.pack("<20H", 1, 1, 2, 0, 0, 3, 2, 4, 1, 0, 0, 0, 2, 1, 0, 2, 1, 4, 2, 0)
    b = b"PTG@" + struct.pack("<IIIHHHH", 0x20, 0x20 + len(verts), len(block), 6, 3, 1, 1) + b"\0" * 8 + verts + block
    out = ptx.ptg(b)
    assert out.shape == (3, 6, 4)
    assert tuple(out[0, 2]) == (255, 0, 0, 255)  # first piece
    assert tuple(out[1, 2]) == (0, 0, 255, 255)  # second piece, though its v (0) is above the first quad's
    assert out[2, 2, 3] == 0 and out[0, 0, 3] == 0  # outside the quads
