"""Dump PTX textures at given offsets as PNGs (zoomed, on grey):
python tools/id3_dump.py OUTDIR OFFHEX.. [--zoom N] [--file ID (default 3)]"""
import sys
from pathlib import Path
from PIL import Image
import ptx
args = sys.argv[1:]
opt = {"--zoom": 3, "--file": 3}
for k in opt:
    if k in args:
        i = args.index(k)
        opt[k] = int(args[i + 1])
        del args[i:i + 2]
zoom = opt["--zoom"]
out = Path(args[0])
out.mkdir(parents=True, exist_ok=True)
b = (Path(__file__).resolve().parents[1] / "work" / "re" / "files" / f"{opt['--file']:05d}.bin").read_bytes()
for o in args[1:]:
    a = ptx.decode(b, ptx.parse(b, int(o, 16)))
    bg = Image.new("RGBA", (a.shape[1], a.shape[0]), (128, 128, 128, 255))
    bg.alpha_composite(Image.fromarray(a))
    bg.resize((a.shape[1] * zoom, a.shape[0] * zoom), Image.NEAREST).save(out / f"{o}.png")
    print(o, a.shape[1], a.shape[0])
