"""PTX@ textures (CLUT4/CLUT8, ABGR8888 palette, optional PSP swizzle) and a scan for them inside containers.

    python -X utf8 tools/ptx.py sheet OUT.png FILE [FILE ...]   # one PNG per sheet, every PTX@ in the files

Header: +4 log2 tw, +5 log2 th, +6 u16 stride px, +8 u16 used w, +A u16 h, +C GE format (4/5), +D swizzled,
+E clut format (3 = 8888), +10 u32 colours, +14 15 - log2 tw, +15 15 - log2 th, +18 u32 palette offset,
+1C u32 pixel offset.
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
    +10 u16 w, h, +14 u16 sprite count per piece. Vertices are GE sprite pairs (top-left, bottom-right) of u16
    u, v, x, y, z; the first count[0] sprites read piece 0, the next count[1] piece 1, with u, v from that piece's
    top-left (verified: chapter cards 1582-1588, last 8 rows from the 448x8 second piece; event banners 1955.., whose
    second piece starts at u 0 on the same v). Sprite = (k, u0, v0, u1, v1, x0, y0, x1, y1).
    """
    vo, to, size = struct.unpack_from("<III", b, o + 4)
    base = o + to
    block = bytes(b[base:base + size]) if size else bytes(b[base:])
    pieces = scan(block) if size else [parse(block)]
    v = list(struct.iter_unpack("<5H", b[o + vo:o + vo + (to - vo) // 10 * 10]))
    # +0x14: u16 sprite count per piece (all 1991 PTGs: the counts sum to the vertex pairs, at most 2 pieces)
    ks = [k for k, c in enumerate(struct.unpack_from("<6H", b, o + 0x14)) for _ in range(c)]
    sprites = [(ks[i], u0, v0, u1, v1, x0, y0, x1, y1)
               for i, ((u0, v0, x0, y0, _), (u1, v1, x1, y1, _)) in enumerate(zip(v[::2], v[1::2])) if i < len(ks)]
    return base, pieces, sprites


def ptg_resize(b, o, w, h, spans=None):
    """Rebuild the PTG@ at o in bytearray b for a w x h image, in place: one PTX piece (piece 0's header and palette,
    its strip width, as many 8-row strips as the bands need, blank pixels), an exact vertex table, then
    ptg_relayout. The file grows or shrinks; a PTP container's later entry offsets move with it (16-aligned).
    The pixels are written afterwards (gfx.write). Used where the old atlas is too small for the English.
    spans: per 8-row band, the (x0, x1) runs to keep (the rest is clear and gets no sprite); default the whole width."""
    spans = spans or [[(0, w)]] * ((h + 7) // 8)
    vo, to, size = struct.unpack_from("<III", b, o + 4)
    base, pieces, sprites = ptg_parts(b, o)
    t = pieces[0]
    old_end = base + size if size else t["do"] + base + stride(t) * ((t["h"] + 7) & ~7)
    sw = t["w"]
    strips, x, n = 1, 0, 0   # count strips and sprites the bands need (same packing as ptg_relayout)
    for left in [x1 - x0 for band in spans for x0, x1 in band]:
        while left:
            k = min(left, sw - x)
            left, x, n = left - k, x + k, n + 1
            if x == sw:
                strips, x = strips + 1, 0
    strips -= x == 0
    rows = strips * 8
    po, do = t["po"] - t["off"], t["do"] - t["off"]
    piece = bytearray(b[base + t["off"]:base + t["off"] + do])
    piece[5] = max(3, (rows - 1).bit_length())   # log2 texture height
    piece[0x15] = 15 - piece[5]   # +14, +15 = 15 - log2 w, 15 - log2 h in every PTX (the game draws garbage otherwise)
    struct.pack_into("<H", piece, 0xA, rows)
    piece += bytes(stride(t) * rows)
    table = (0x20 + 20 * n + 15) & ~15
    head = bytearray(b[o:o + 0x20])
    struct.pack_into("<III", head, 4, 0x20, table, len(piece) if size else 0)
    new = head + bytes(table - 0x20) + piece
    new += bytes(-len(new) % 16)
    old_len = old_end - o
    old_len += -old_len % 16
    if b[:4] == b"PTP\0":   # entry offsets from +0x10: the PTG runs to the next entry
        cnt = struct.unpack_from("<I", b, 4)[0]
        ents = struct.unpack_from(f"<{cnt}I", b, 0x10)
        old_len = min([e for e in ents if e > o] + [len(b)]) - o
        for i, e in enumerate(ents):
            if e > o:
                struct.pack_into("<I", b, 0x10 + 4 * i, e + len(new) - old_len)
    b[o:o + old_len] = new
    ptg_relayout(b, o, w, h, spans)


def ptg_relayout(b, o, w, h, spans=None):
    """Rewrite the PTG@ at o in bytearray b as a w x h image: header size, per-piece counts and vertices, with the
    bands packed in order through the pieces' 8-row strips (a band that runs off a strip continues on the next).
    The PTX pieces are untouched, so the pixels are written afterwards (gfx.write). Fails if the atlas or the vertex
    table is too small; unused vertex slots are zeroed (the game reads the counts)."""
    spans = spans or [[(0, w)]] * ((h + 7) // 8)
    vo, to, _ = struct.unpack_from("<III", b, o + 4)
    _, pieces, _ = ptg_parts(b, o)
    strips = [(k, r * 8, t["w"]) for k, t in enumerate(pieces) for r in range(t["h"] // 8)]
    sprites, s, u = [], 0, 0
    for y, x, end in [(8 * i, x0, x1) for i, band in enumerate(spans) for x0, x1 in band]:
        while x < end:
            assert s < len(strips), f"atlas too small for {w}x{h}"
            k, v, sw = strips[s]
            n, rows = min(end - x, sw - u), min(8, h - y)   # the last band of a height that isn't a multiple of 8
            sprites.append((k, u, v, u + n, v + rows, x, y, x + n, y + rows))
            x, u = x + n, u + n
            if u == sw:
                s, u = s + 1, 0
    cap = (to - vo) // 20
    assert len(sprites) <= cap, f"{len(sprites)} sprites, room for {cap}"
    counts = [sum(1 for sp in sprites if sp[0] == k) for k in range(6)]
    struct.pack_into("<HH6H", b, o + 0x10, w, h, *counts)
    table = b"".join(struct.pack("<10H", u0, v0, x0, y0, 0, u1, v1, x1, y1, 0)
                     for _, u0, v0, u1, v1, x0, y0, x1, y1 in sprites)
    b[o + vo:o + to] = table + bytes(to - vo - len(table))


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
