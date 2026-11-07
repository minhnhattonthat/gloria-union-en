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


def test_second_piece_shares_the_palette():
    b = tex(4, 2, bytes(8), [RED, BLUE]) + tex(4, 2, bytes([1]) * 8)
    a, c = ptx.scan(b)
    assert c["po"] == a["po"]
    assert tuple(ptx.decode(b, c)[0, 0]) == (0, 0, 255, 255)


def test_ptg_stacks_pieces_and_places_quads():
    block = tex(4, 2, bytes(8), [RED, BLUE]) + tex(4, 2, bytes([1]) * 8)
    # one quad: atlas (1,1)-(3,3) crosses both pieces, drawn at (2,0)-(4,2)
    verts = struct.pack("<10H", 1, 1, 2, 0, 0, 3, 3, 4, 2, 0)
    b = b"PTG@" + struct.pack("<IIIHH", 0x20, 0x20 + len(verts), len(block), 6, 3) + b"\0" * 12 + verts + block
    out = ptx.ptg(b)
    assert out.shape == (3, 6, 4)
    assert tuple(out[0, 2]) == (255, 0, 0, 255)  # row 1 of the atlas: first piece
    assert tuple(out[1, 2]) == (0, 0, 255, 255)  # row 2 of the atlas: second piece
    assert out[2, 2, 3] == 0 and out[0, 0, 3] == 0  # outside the quad
