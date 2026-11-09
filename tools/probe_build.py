"""Probe build: chosen PTX textures filled with loud stripes, to see whether any screen draws them.

    python -X utf8 tools/probe_build.py OUT.iso FILE:OFFHEX [FILE:OFFHEX ...]

Builds the English build (build.py) with the textures overwritten by alternating rows of the palette colours nearest
magenta and black, then warp to the suspected scenes on OUT.iso. Never ship OUT.iso.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
import gfx  # noqa: E402


def stripes(b, a):
    t = gfx.read(b, a)
    pal = gfx.palette(b, a)
    out = np.zeros_like(t)
    out[0::2] = gfx.quantize(np.full((1, 1, 4), (255, 0, 255, 255), np.uint8), pal)[0, 0]
    out[1::2] = gfx.quantize(np.full((1, 1, 4), (0, 0, 0, 255), np.uint8), pal)[0, 0]
    return out


def main():
    out, probes = Path(sys.argv[1]), [(int(f), int(o, 16)) for f, o in (p.split(":") for p in sys.argv[2:])]
    assert probes, __doc__
    apply = gfx.apply

    def probed(repl):
        repl = apply(repl)
        for fid, off in probes:
            a = dict(name=f"probe{fid}_{off:x}", file=fid, kind="ptx", off=off, rect=None, draw=None, resize=False,
                     table=None, section=None, trim=False, used=False)
            b = bytearray(repl.get(fid) or (gfx.FILES / f"{fid:05d}.bin").read_bytes())
            gfx.write(b, a, stripes(bytes(b), a))
            repl[fid] = bytes(b)
        return repl

    gfx.apply = probed
    print(build.build(out))


if __name__ == "__main__":
    main()
