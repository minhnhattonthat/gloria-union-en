"""find_tex for PTG composites: which PTG holds a patch of a screenshot at 1:1.
python tools/find_ptg.py SHOT.png x,y,w,h [--files 3,2023] [--top 5]   (mean abs RGB diff over opaque texels; 0 = exact)"""
import argparse
import struct
from pathlib import Path
import numpy as np
from PIL import Image
from numpy.lib.stride_tricks import sliding_window_view
import ptx

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("shot")
ap.add_argument("rect")
ap.add_argument("--files", default="3")
ap.add_argument("--top", type=int, default=5)
a = ap.parse_args()
x, y, w, h = map(int, a.rect.split(","))
patch = np.asarray(Image.open(a.shot).convert("RGB")).astype(np.int16)[y:y + h, x:x + w]
best = []
for f in map(int, a.files.split(",")):
    b = (ROOT / "work" / "re" / "files" / f"{f:05d}.bin").read_bytes()
    p = 0
    while (p := b.find(b"PTG@", p)) >= 0:
        try:
            img = ptx.ptg(b, p)
        except Exception:
            p += 4
            continue
        if img.shape[0] >= h and img.shape[1] >= w:
            rgb = sliding_window_view(img[..., :3].astype(np.int16), (h, w, 3))[..., 0, :, :, :]
            op = sliding_window_view(img[..., 3] > 200, (h, w))
            n = op.sum((2, 3))
            d = (np.abs(rgb - patch).sum(-1) * op).sum((2, 3)) / np.maximum(n * 3, 1)
            d[n < h * w * 0.8] = 1e9
            v, u = np.unravel_index(d.argmin(), d.shape)
            best.append((d[v, u], f, p, img.shape[1], img.shape[0], u, v))
        p += 4
for d, f, p, iw, ih, u, v in sorted(best)[:a.top]:
    print(f"diff {d:6.1f}  id {f} PTG +{p:#x} {iw}x{ih} at u={u} v={v}")
