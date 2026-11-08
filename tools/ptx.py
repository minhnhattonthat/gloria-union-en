"""PTX@ textures (CLUT4/CLUT8, ABGR8888 palette, optional PSP swizzle) and a scan for them inside containers.

    python -X utf8 tools/ptx.py sheet OUT.png FILE [FILE ...]   # one PNG per sheet, every PTX@ in the files

Header: +4 log2 tw, +5 log2 th, +6 u16 stride px, +8 u16 used w, +A u16 h, +C GE format (4/5), +D swizzled,
+E clut format (3 = 8888), +10 u32 colours, +18 u32 palette offset, +1C u32 pixel offset.
"""
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw


def parse(b, o=0):
    if b[o:o + 4] != b"PTX@" or o + 0x20 > len(b):
        return None
    lw, lh, w, used, h, fmt, sw, cf = struct.unpack_from("<BBHHHBBB", b, o + 4)
    n = struct.unpack_from("<I", b, o + 0x10)[0]
    po, do = struct.unpack_from("<II", b, o + 0x18)
    if fmt not in (4, 5) or cf != 3 or not (2 <= n <= 256) or not (0 < w <= 1024 and 0 < h <= 1024):
        return None
    if o + po + n * 4 > len(b) or o + do >= len(b):  # a stray "PTX@" in other data
        return None
    return dict(off=o, lw=lw, lh=lh, w=w, used=used, h=h, fmt=fmt, sw=sw, n=n, po=o + po, do=o + do)


def unswizzle(raw, rowbytes, rows):
    """PSP 16x8-byte blocks. rowbytes must be a multiple of 16; rows a multiple of 8."""
    out = np.zeros(rowbytes * rows, dtype=np.uint8)
    src = np.frombuffer(raw, dtype=np.uint8)
    p = 0
    for y in range(0, rows, 8):
        for x in range(0, rowbytes, 16):
            for r in range(8):
                out[(y + r) * rowbytes + x:(y + r) * rowbytes + x + 16] = src[p:p + 16]
                p += 16
    return out


def swizzle(lin, rowbytes, rows):
    """Inverse of unswizzle: linear rows -> PSP 16x8-byte blocks."""
    src = np.asarray(lin, dtype=np.uint8).reshape(rows, rowbytes)
    return src.reshape(rows // 8, 8, rowbytes // 16, 16).transpose(0, 2, 1, 3).tobytes()


def encode(b, t, rgba, nearest=False):
    """New pixel bytes for texture t (same size, same palette) drawing the h x w x 4 image rgba. Each colour must be in
    the palette (the first index holding it wins) unless nearest; padding columns and rows keep their old bytes.
    Write back with b[t['do']:t['do'] + len(out)] = out."""
    bpp = 8 if t["fmt"] == 5 else 4
    rb = stride(t)
    rows = (t["h"] + 7) & ~7 if t["sw"] else t["h"]
    raw = bytes(b[t["do"]:t["do"] + rb * rows]).ljust(rb * rows, b"\0")
    lin = (unswizzle(raw, rb, rows) if t["sw"] else np.frombuffer(raw, dtype=np.uint8)).reshape(rows, rb).copy()
    pal = np.frombuffer(bytes(b), dtype=np.uint8, count=t["n"] * 4, offset=t["po"]).reshape(-1, 4).astype(int)
    img = np.asarray(rgba, dtype=int)
    assert img.shape == (t["h"], t["w"], 4), (img.shape, t["h"], t["w"])
    d = np.abs(img[:, :, None, :] - pal[None, None, :, :]).sum(3)   # h x w x n distances
    idx = d.argmin(2).astype(np.uint8)   # argmin takes the first of equal colours
    if not nearest and (bad := d.min(2) > 0).any():
        y, x = np.argwhere(bad)[0]
        raise ValueError(f"{bad.sum()} pixels not in the palette, first at ({x},{y}): {tuple(img[y, x])}")
    if bpp == 4:
        px = np.zeros((rows, rb * 2), dtype=np.uint8)
        px[:, 0::2], px[:, 1::2] = lin & 15, lin >> 4
        px[:t["h"], :t["w"]] = idx
        lin = (px[:, 0::2] | (px[:, 1::2] << 4)).astype(np.uint8)
    else:
        lin[:t["h"], :t["w"]] = idx
    return swizzle(lin, rb, rows) if t["sw"] else lin.tobytes()


def stride(t):
    bpp = 8 if t["fmt"] == 5 else 4
    rb = (t["w"] * bpp + 7) // 8
    return (rb + 15) & ~15 if t["sw"] else rb


def decode(b, t):
    """-> h x w x 4 uint8 array."""
    bpp = 8 if t["fmt"] == 5 else 4
    rb = stride(t)
    rows = (t["h"] + 7) & ~7 if t["sw"] else t["h"]
    raw = b[t["do"]:t["do"] + rb * rows]
    raw = raw.ljust(rb * rows, b"\0")
    lin = unswizzle(raw, rb, rows) if t["sw"] else np.frombuffer(raw, dtype=np.uint8)
    lin = lin.reshape(rows, rb)
    if bpp == 4:
        px = np.zeros((rows, rb * 2), dtype=np.uint8)
        px[:, 0::2] = lin & 15
        px[:, 1::2] = lin >> 4
    else:
        px = lin
    if t["po"] == t["off"]:  # palette kept outside the PTX (PTA animations): grey ramp, index 0 clear
        pal = np.full((256, 4), 255, dtype=np.uint8)
        pal[:, :3] = (np.arange(256) * 255 // max(t["n"] - 1, 1)).clip(0, 255)[:, None]
        pal[0, 3] = 0
    else:
        pal = np.frombuffer(b, dtype=np.uint8, count=t["n"] * 4, offset=t["po"]).reshape(-1, 4).copy()
        pal = np.vstack([pal, np.zeros((256 - len(pal), 4), dtype=np.uint8)])
    return pal[px[:t["h"], :t["w"]]]


def scan(b):
    out, p, pal = [], 0, None
    while True:
        p = b.find(b"PTX@", p)
        if p < 0:
            return out
        t = parse(b, p)
        if t:
            # palette offset 0: the piece of a split texture shares the previous piece's palette
            if t["po"] == p and pal is not None:
                t["po"] = pal
            pal = t["po"]
            out.append(t)
        p += 4


def ptg_parts(b, o=0):
    """(block start, PTX pieces with offsets relative to the block, sprites) of the PTG@ at o.

    Header: +4 vertex offset, +8 PTX block offset, +C its size (0 = one PTX at the offset, length unrecorded),
    +10 u16 w, h. Vertices are GE sprite pairs (top-left, bottom-right) of u16 u, v, x, y, z. Each sprite reads
    piece k; v counts from the top of that piece, so v going back down means the next piece (verified: chapter
    cards 1582-1588, whose last 8 rows come from the 448x8 second piece). A scan of all 1991 PTGs in the CPK: 857
    restart v, none reads past piece 0's height. Sprite = (k, u0, v0, u1, v1, x0, y0, x1, y1).
    """
    vo, to, size = struct.unpack_from("<III", b, o + 4)
    base = o + to
    block = bytes(b[base:base + size]) if size else bytes(b[base:])
    pieces = scan(block) if size else [parse(block)]
    v = list(struct.iter_unpack("<5H", b[o + vo:o + vo + (to - vo) // 10 * 10]))
    sprites, k, last = [], 0, 0
    for (u0, v0, x0, y0, _), (u1, v1, x1, y1, _) in zip(v[::2], v[1::2]):
        if v0 < last and k + 1 < len(pieces):   # v restarted: the next piece
            k += 1
        last = v0
        sprites.append((k, u0, v0, u1, v1, x0, y0, x1, y1))
    return base, pieces, sprites


def ptg(b, o=0):
    """Composite the PTG@ sprite at o -> h x w x 4 (layout: ptg_parts)."""
    w, h = struct.unpack_from("<HH", b, o + 0x10)
    base, pieces, sprites = ptg_parts(b, o)
    block = bytes(b[base:])
    tex = [decode(block, t) for t in pieces]
    # the last band can run past the header's height: padding rows of the 8-px grid
    out = np.zeros((max([h] + [s[8] for s in sprites]), max([w] + [s[7] for s in sprites]), 4), dtype=np.uint8)
    for k, u0, v0, u1, v1, x0, y0, x1, y1 in sprites:
        out[y0:y1, x0:x1] = tex[k][v0:v1, u0:u1]
    return out


def sheet(items, path, cell=160, cols=8, zoom_small=False):
    """items: (label, rgba array). Magenta-ish background shows alpha holes."""
    rows = -(-len(items) // cols)
    im = Image.new("RGB", (cols * cell, rows * (cell + 12)), (60, 40, 70))
    dr = ImageDraw.Draw(im)
    for i, (lab, a) in enumerate(items):
        tile = Image.fromarray(a, "RGBA")
        tile.thumbnail((cell - 2, cell - 2))
        x, y = (i % cols) * cell, (i // cols) * (cell + 12)
        im.paste(tile, (x + 1, y + 12), tile)
        dr.text((x + 1, y), lab, fill=(255, 255, 0))
    im.save(path)


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        items = []
        for f in sys.argv[3:]:
            b = open(f, "rb").read()
            name = f.replace("\\", "/").split("/")[-1].split(".")[0]
            for t in scan(b):
                items.append(("%s+%x %dx%d" % (name, t["off"], t["w"], t["h"]), decode(b, t)))
        sheet(items, sys.argv[2])
        print(len(items), "textures")
