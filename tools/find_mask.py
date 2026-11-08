"""Which texture holds light lettering seen over a see-through background (find_tex.py needs opaque texels):
python tools/find_mask.py SHOT.png x,y,w,h [--files 3] [--top 5] [--light 200]
Binarizes the patch (all RGB > light) and every PTX (alpha > 128 and all RGB > light), slides the patch over each
texture at 1:1 and prints the best matches as mismatching pixels / patch size (0 = exact)."""
import argparse
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
ap.add_argument("--light", type=int, default=200)
ap.add_argument("--dark", type=int, default=0, help="match dark lettering instead: all RGB < DARK")
o = ap.parse_args()
x, y, w, h = map(int, o.rect.split(","))


def ink(rgb):
    return (rgb < o.dark).all(-1) if o.dark else (rgb > o.light).all(-1)


p = ink(np.array(Image.open(o.shot).convert("RGB"))[y:y + h, x:x + w].astype(int))
assert p.any(), "no light pixels in the patch"
hits = []
for fid in map(int, o.files.split(",")):
    b = (ROOT / "work" / "re" / "files" / f"{fid:05d}.bin").read_bytes()
    texs = [(t, lambda t=t: ptx.decode(b, t)) for t in ptx.scan(b)]
    i = b.find(b"PTG@")
    while i != -1:   # PTG composites too (their PTX pieces are packed strips)
        w0, h0 = int.from_bytes(b[i + 16:i + 18], "little"), int.from_bytes(b[i + 18:i + 20], "little")
        texs.append((dict(off=i, w=w0, h=h0), lambda i=i: ptx.ptg(b, i)))
        i = b.find(b"PTG@", i + 4)
    for t, dec in texs:
        if t["w"] < w or t["h"] < h:
            continue
        try:
            a = dec()
        except Exception:
            continue
        if a.shape[0] < h or a.shape[1] < w:
            continue
        m = (a[..., 3] > 128) & ink(a[..., :3].astype(int))
        d = (sliding_window_view(m, (h, w)) != p).mean(axis=(2, 3))
        j = np.unravel_index(d.argmin(), d.shape)
        hits.append((float(d[j]), fid, t["off"], t["w"], t["h"], int(j[1]), int(j[0])))
for s, fid, off, tw, th, u, v in sorted(hits)[:o.top]:
    print(f"miss {s:5.3f}  id {fid} +{off:#x} {tw}x{th} at u={u} v={v}")
