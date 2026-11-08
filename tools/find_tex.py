"""Which texture holds a patch of a screenshot: python tools/find_tex.py SHOT.png x,y,w,h [--files 3,4] [--top 5]
Slides the patch over every PTX of the files (default id 3) at 1:1 and prints the best matches (mean abs RGB difference
over opaque texels; 0 = exact). Pick an opaque patch (no see-through edges), 8-16 px square, on a stroke of the text."""
import argparse
import sys
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
o = ap.parse_args()
x, y, w, h = map(int, o.rect.split(","))
p = np.array(Image.open(o.shot).convert("RGB"))[y:y + h, x:x + w].astype(np.int16)
hits = []
for fid in map(int, o.files.split(",")):
    b = (ROOT / "work" / "re" / "files" / f"{fid:05d}.bin").read_bytes()
    for t in ptx.scan(b):
        if t["w"] < w or t["h"] < h:
            continue
        try:
            a = ptx.decode(b, t)
        except Exception:
            continue
        rgb = a[..., :3].astype(np.int16)
        win = sliding_window_view(rgb, (h, w, 3))[..., 0, :, :, :]   # (H-h+1, W-w+1, h, w, 3)
        d = np.abs(win - p).mean(axis=(2, 3, 4))
        opaque = sliding_window_view(a[..., 3] > 200, (h, w)).mean(axis=(2, 3))
        d[opaque < 0.9] = 999
        j = np.unravel_index(d.argmin(), d.shape)
        hits.append((float(d[j]), fid, t["off"], t["w"], t["h"], int(j[1]), int(j[0])))
for s, fid, off, tw, th, u, v in sorted(hits)[:o.top]:
    print(f"diff {s:6.1f}  id {fid} +{off:#x} {tw}x{th} at u={u} v={v}")
sys.exit(0)
