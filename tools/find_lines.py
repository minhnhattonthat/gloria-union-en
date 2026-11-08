"""Candidate lettering lines in a texture: light fill (yellow or white) with a dark rim, grouped into line boxes.

    python -X utf8 tools/find_lines.py IMG.png.. [--out DIR]   (prints "n x y w h" per box; DIR: the image x2 with
                                                                numbered boxes, to pick rects for gfx/*.tsv by eye)
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def lines(a):
    px = a[..., :3].astype(int)
    op = a[..., 3] > 200
    light = op & (((px[..., 0] > 200) & (px[..., 1] > 160) & (px[..., 2] < 150)) | (px.min(2) > 225))
    dark = op & (px.max(2) < 70)
    near = ndimage.binary_dilation(dark, iterations=2)
    m = ndimage.binary_dilation(light & near, np.ones((3, 9), bool))
    lab, n = ndimage.label(m)
    out = []
    for sl in ndimage.find_objects(lab):
        y, x = sl[0].start, sl[1].start
        h, w = sl[0].stop - y, sl[1].stop - x
        if 7 <= h <= 24 and w >= 10:
            out.append((x, y, w, h))
    return sorted(out, key=lambda r: (r[1], r[0]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("imgs", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args()
    for p in a.imgs:
        img = np.asarray(Image.open(p).convert("RGBA"))
        boxes = lines(img)
        print(Path(p).stem, " ".join(f"{i}:{x},{y},{w},{h}" for i, (x, y, w, h) in enumerate(boxes)))
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            bg = Image.new("RGBA", (img.shape[1], img.shape[0]), (60, 0, 60, 255))
            bg.alpha_composite(Image.fromarray(img))
            im = bg.resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST)
            d = ImageDraw.Draw(im)
            for i, (x, y, w, h) in enumerate(boxes):
                d.rectangle((2 * x, 2 * y, 2 * (x + w) - 1, 2 * (y + h) - 1), outline=(255, 0, 0, 255))
                d.text((2 * x + 1, 2 * y - 9), str(i), fill=(0, 255, 0, 255))
            im.convert("RGB").save(Path(a.out) / f"{Path(p).stem}.png")
