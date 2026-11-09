"""Skill cut-in text textures (55 files, odd ids 297-404: one 288x230 PTX at +0; the even ids are the 256x272 cards).

    python -X utf8 tools/cutins.py OUT.png FROM TO [--div 2]    # every text PTX in the range, on grey, 3 columns
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gfx, ptx
out, lo, hi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
div = 2 if "--div" in sys.argv else 1
tiles = []
for f in range(lo, hi + 1):
    p = gfx.FILES / f"{f:05d}.bin"
    if not p.exists(): continue
    b = p.read_bytes()
    if b[:4] != b"PTX@": continue
    t = ptx.parse(b, 0)
    if (t["w"], t["h"]) != (288, 230): continue
    tiles.append((f, ptx.decode(b, t)))
cols = 3
W, H = 288 // div + 4, 230 // div + 4
im = Image.new("RGB", (W * cols, H * (-(-len(tiles) // cols))), (0, 0, 0))
d = ImageDraw.Draw(im)
for i, (f, a) in enumerate(tiles):
    p = Image.fromarray(a)
    bg = Image.new("RGBA", p.size, (60, 70, 90, 255)); bg.alpha_composite(p)
    bg = bg.resize((288 // div, 230 // div), Image.LANCZOS)
    x, y = W * (i % cols), H * (i // cols)
    im.paste(bg.convert("RGB"), (x, y)); d.text((x + 2, y + 2), str(f), fill=(0, 255, 0))
im.save(out)
print(len(tiles), [f for f, _ in tiles])
