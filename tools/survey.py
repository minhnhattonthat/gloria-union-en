"""Contact sheets of every unique image for the graphics-text survey.

    python -X utf8 tools/survey.py OUTDIR [--sample 6] [--first N] [--last N]

Takes each PTX@ in work/re/files, each PNG inside them, and the ISO's ICON0/PIC1 art. Sides up to 300 px are drawn
1:1, larger ones at 1/2, so text stays readable. Unique means the same pixel bytes and size. Only frames of PTG@
sprite sets are sampled (every N-th); all else is kept. Prints what it dropped and why. Writes sheet_NN.png and
index.tsv (sheet, x, y, id, offset, w, h, owner).
"""
import argparse
import collections
import hashlib
import io
import os
import struct
import sys
import warnings

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import ptx  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)
SHEET = (1600, 1200)
LABEL = 12


def ptg_spans(b):
    """(PTG offset, start, end of its PTX block) of each PTG@ in b."""
    spans, p = [], 0
    while (p := b.find(b"PTG@", p)) >= 0:
        off, size = struct.unpack_from("<II", b, p + 8)
        spans.append((p, p + off, p + off + max(size, 1)))
        p += 4
    return spans


def images(a):
    """Yield (id, off, w, h, owner, rgba); count drops in `dropped`."""
    seen = set()

    def fresh(data):
        key = hashlib.md5(data).digest()
        if key in seen:
            dropped["same pixels as an earlier image"] += 1
            return False
        seen.add(key)
        return True

    for i in range(a.first, a.last + 1):
        b = open(f"work/re/files/{i:05d}.bin", "rb").read()
        spans, frame, run = ptg_spans(b), 0, None
        for o, _, _ in spans:
            rgba = ptx.ptg(b, o)
            if not rgba[..., 3].any():
                dropped["PTG@ with no opaque pixels"] += 1
            elif fresh(rgba.tobytes()):
                run, frame = rgba.shape, frame + 1 if rgba.shape == run else 0
                if frame % a.sample:  # animation frames share a size
                    dropped[f"PTG@ frame, sampled 1 in {a.sample}"] += 1
                else:
                    yield i, o, rgba.shape[1], rgba.shape[0], "PTG", rgba
        for t in ptx.scan(b):
            if any(s <= t["off"] < e for _, s, e in spans):
                continue
            rb, rows = ptx.stride(t), (t["h"] + 7) & ~7 if t["sw"] else t["h"]
            if fresh(b[t["do"]:t["do"] + rb * rows] + struct.pack("<HH", t["w"], t["h"])):
                yield i, t["off"], t["w"], t["h"], "PTX", ptx.decode(b, t)
        p = 0
        while (p := b.find(b"\x89PNG\r\n\x1a\n", p)) >= 0:
            im = Image.open(io.BytesIO(b[p:])).convert("RGBA")
            yield i, p, im.width, im.height, "PNG", np.array(im)
            p += 8
    for name in ("PSP_GAME/ICON0.PNG", "PSP_GAME/PIC1.PNG", "PSP_GAME/INSDIR/ICON0.PNG"):
        im = Image.open("work/iso/" + name).convert("RGBA")
        yield name, 0, im.width, im.height, "ISO", np.array(im)


def flush(im, n, out):
    im.save(f"{out}/sheet_{n:02d}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--sample", type=int, default=6)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--last", type=int, default=2964)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    blank = lambda: Image.new("RGB", SHEET, (60, 40, 70))  # noqa: E731
    im, n, x, y, row, count = blank(), 0, 0, 0, 0, 0
    with open(f"{a.out}/index.tsv", "w", encoding="utf-8", newline="\n") as idx:
        for i, off, w, h, owner, rgba in images(a):
            tile = Image.fromarray(rgba, "RGBA")
            if max(w, h) > 300:
                tile = tile.resize((w // 2, h // 2), Image.LANCZOS)
            lab = f"{i}+{off:x}"
            tw = max(tile.width, 6 * len(lab) + 2) + 4
            if x + tw > SHEET[0]:
                x, y, row = 0, y + row, 0
            if y + tile.height + LABEL > SHEET[1]:
                flush(im, n, a.out)
                im, n, x, y, row = blank(), n + 1, 0, 0, 0
            ImageDraw.Draw(im).text((x + 1, y), lab, fill=(255, 255, 0))
            im.paste(tile, (x + 1, y + LABEL), tile)
            idx.write(f"{n}\t{x}\t{y}\t{i}\t{off:x}\t{w}\t{h}\t{owner}\n")
            x += tw
            row = max(row, tile.height + LABEL + 2)
            count += 1
    flush(im, n, a.out)
    print(count, "images,", n + 1, "sheets")
    for why, k in dropped.most_common():
        print(f"dropped {k}: {why}")


dropped = collections.Counter()
if __name__ == "__main__":
    main()
