"""Ink bbox (alpha>128) of regions of a PTX, for gfx.fixed rects:
python tools/id3_inkbox.py [--file ID (default 3)] OFFHEX y0-y1[:x0-x1] ..."""
import sys
from pathlib import Path
import numpy as np
import ptx
fid = 3
if sys.argv[1] == "--file":
    fid = int(sys.argv[2])
    del sys.argv[1:3]
b = (Path(__file__).resolve().parents[1] / "work" / "re" / "files" / f"{fid:05d}.bin").read_bytes()
a = ptx.decode(b, ptx.parse(b, int(sys.argv[1], 16)))
print("size", a.shape[1], a.shape[0])
for spec in sys.argv[2:]:
    ys, _, xs = spec.partition(":")
    y0, y1 = map(int, ys.split("-"))
    x0, x1 = map(int, xs.split("-")) if xs else (0, a.shape[1] - 1)
    ink = a[y0:y1 + 1, x0:x1 + 1, 3] > 128
    yy, xx = np.where(ink)
    print(spec, "->", (int(xx.min() + x0), int(yy.min() + y0), int(xx.max() - xx.min() + 1), int(yy.max() - yy.min() + 1)))
