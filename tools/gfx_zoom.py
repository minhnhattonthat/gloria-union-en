"""Original vs redrawn gfx assets side by side on grey, zoomed:
python -X utf8 tools/gfx_zoom.py OUT.png NAME.. [--zoom N]"""
import sys
from pathlib import Path
from PIL import Image
import gfx

args = sys.argv[1:]
zoom = 3
if "--zoom" in args:
    i = args.index("--zoom")
    zoom = int(args[i + 1])
    del args[i:i + 2]
out, names = args[0], args[1:]
pairs = []
for n in names:
    for im in (Image.fromarray(gfx.original(n)), Image.open(gfx.GFX / f"{n}.png").convert("RGBA")):
        bg = Image.new("RGBA", im.size, (96, 120, 96, 255))
        bg.alpha_composite(im)
        pairs.append(bg)
w = max(p.width for p in pairs[0::2]) + max(p.width for p in pairs[1::2]) + 6
h = sum(max(a.height, b.height) + 4 for a, b in zip(pairs[0::2], pairs[1::2]))
sheet = Image.new("RGBA", (w, h), (30, 30, 30, 255))
y = 0
for a, b in zip(pairs[0::2], pairs[1::2]):
    sheet.paste(a, (0, y))
    sheet.paste(b, (w - b.width, y))
    y += max(a.height, b.height) + 4
sheet.resize((w * zoom, h * zoom), Image.NEAREST).save(out)
print(out, w * zoom, h * zoom)
