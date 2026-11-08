"""Every PTG@ in a file, in file order, with its size; --sheet OUT renders a range as numbered rows (zoomed) to read
the lettering: python tools/ptg_list.py 2430 [--from 66 --to 275] [--sheet work/gfx/x.png] [--zoom 2] [--cols 2]"""
import argparse
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gfx  # noqa: E402
import ptx  # noqa: E402


def offsets(b):
    out, i = [], b.find(b"PTG@")
    while i != -1:
        out.append(i)
        i = b.find(b"PTG@", i + 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=int)
    ap.add_argument("--from", dest="lo", type=int, default=0)
    ap.add_argument("--to", dest="hi", type=int, default=10 ** 6)
    ap.add_argument("--sheet")
    ap.add_argument("--zoom", type=int, default=2)
    ap.add_argument("--cols", type=int, default=2)
    a = ap.parse_args()
    b = (gfx.FILES / f"{a.file:05d}.bin").read_bytes()
    offs = offsets(b)
    rows = []
    for n, o in enumerate(offs):
        if not a.lo <= n <= a.hi:
            continue
        w, h = struct.unpack_from("<2H", b, o + 0x10)
        print(n, hex(o), w, h)
        if a.sheet:
            rows.append((n, o, ptx.ptg(b, o)))
    if a.sheet and rows:
        cw = max(r[2].shape[1] for r in rows) * a.zoom + 40
        ch = max(r[2].shape[0] for r in rows) * a.zoom + 2
        nr = -(-len(rows) // a.cols)
        im = Image.new("RGB", (cw * a.cols, ch * nr), (90, 90, 90))
        d = ImageDraw.Draw(im)
        for k, (n, o, img) in enumerate(rows):
            x, y = cw * (k // nr), ch * (k % nr)
            p = Image.fromarray(np.asarray(img, np.uint8)).convert("RGBA")
            p = p.resize((p.width * a.zoom, p.height * a.zoom), Image.NEAREST)
            bg = Image.new("RGBA", p.size, (90, 90, 90, 255))
            bg.alpha_composite(p)
            im.paste(bg.convert("RGB"), (x + 38, y))
            d.text((x + 2, y + 2), str(n), fill=(255, 255, 0))
        im.save(a.sheet)


if __name__ == "__main__":
    main()
