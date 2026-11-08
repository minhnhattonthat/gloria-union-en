"""Ink boxes of a texture, for gfx.fixed rects: bands of rows holding ink (alpha>128), split into x-runs at gaps of
--gap px or more. python -X utf8 tools/ink_runs.py FILE OFFHEX [--gap 8] [--rgap 1]   (prints "x y w h" per run)"""
import argparse
from pathlib import Path

import numpy as np

import ptx

p = argparse.ArgumentParser()
p.add_argument("file", type=int)
p.add_argument("off")
p.add_argument("--gap", type=int, default=8)
p.add_argument("--rgap", type=int, default=1, help="clear rows that still join two bands")
p.add_argument("--rows", nargs="*", default=[], help="y0-y1 bands to split instead of finding them")
args = p.parse_args()
b = (Path(__file__).resolve().parents[1] / "work" / "re" / "files" / f"{args.file:05d}.bin").read_bytes()
o = int(args.off, 16)
t = ptx.parse(b, o)
a = ptx.decode(b, t) if t else ptx.ptg(b, o)
ink = a[..., 3] > 128
print("size", a.shape[1], a.shape[0])


def runs(v, gap):
    idx = np.flatnonzero(v)
    out = []
    for i in idx:
        if out and i - out[-1][1] < gap:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return out


bands = [tuple(int(v) for v in r.split("-")) for r in args.rows] or runs(ink.any(1), args.rgap + 1)
for y0, y1 in bands:
    for x0, x1 in runs(ink[y0:y1].any(0), args.gap):
        yy = np.flatnonzero(ink[y0:y1, x0:x1].any(1))
        print(x0, y0 + yy[0], x1 - x0, yy[-1] - yy[0] + 1)
