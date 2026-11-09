"""Story pages (files 1590-1639: one 384 x H paragraph page at +0x20, white text with a black rim, centred lines).

    python -X utf8 tools/pages.py layout [FID ...]          # line bands and paragraphs per page
    python -X utf8 tools/pages.py sheet OUT.png FID [...]    # the pages zoomed 2x on grey, to transcribe

The game scrolls a page up through a 2-line strip while portraits change per paragraph, so gfx.draw_page keeps each
paragraph's top y and line count. Transcriptions and English: gfx/pages.tsv.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ptx  # noqa: E402

FIRST, LAST = 1590, 1639
OFF, USED = 0x20, 380   # x 380-383 is an opaque black strip outside the drawn width


def page(fid):
    b = (ROOT / "work" / "re" / "files" / f"{fid:05d}.bin").read_bytes()
    return ptx.decode(b, ptx.parse(b, OFF))


def lines(a):
    """(y0, y1, x0, x1) per text line: runs of rows holding white ink (the rim alone does not count)."""
    white = (a[..., 3] > 128) & (a[..., :3].min(2) > 200)
    white[:, USED:] = False
    rows = np.flatnonzero(white.any(1))
    out = []
    for y in rows:
        if out and y - out[-1][1] <= 2:
            out[-1][1] = y + 1
        else:
            out.append([y, y + 1])
    res = []
    for y0, y1 in out:
        xs = np.flatnonzero(white[y0:y1].any(0))
        res.append((int(y0), int(y1), int(xs[0]), int(xs[-1]) + 1))
    return res


def paragraphs(a):
    """Lines grouped where the gap to the next line is no more than the line pitch inside a paragraph."""
    ls = lines(a)
    out = []
    for ln in ls:
        if out and ln[0] - out[-1][-1][1] < 12:
            out[-1].append(ln)
        else:
            out.append([ln])
    return out


def main():
    cmd, *args = sys.argv[1:] or ["layout"]
    if cmd == "layout":
        for fid in map(int, args or range(FIRST, LAST + 1)):
            a = page(fid)
            ps = paragraphs(a)
            print(fid, f"h {a.shape[0]}", " | ".join(f"y{p[0][0]} x{len(p)}" for p in ps))
    elif cmd == "sheet":
        out, fids = args[0], [int(f) for f in args[1:]]
        ims = [Image.fromarray(page(f)).resize((768, page(f).shape[0] * 2), Image.NEAREST) for f in fids]
        c = Image.new("RGBA", (800, sum(i.height + 20 for i in ims)), (90, 90, 90, 255))
        d, y = ImageDraw.Draw(c), 0
        for f, im in zip(fids, ims):
            d.text((4, y + 2), str(f), fill=(255, 255, 0, 255))
            c.alpha_composite(im, (30, y + 16))
            y += im.height + 20
        c.save(out)


if __name__ == "__main__":
    main()
