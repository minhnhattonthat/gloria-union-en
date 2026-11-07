"""List the text windows and fonts a scene draws with: hooks the glyph setter 0xA20E4 (docs/re/text.md §Text renderer).

    python -X utf8 tools/debug/glyphs.py work/states/stage3.ppst [--iso ISO] [--taps 30]

Prints per (window, font): glyph count, window x, y, box w, h, spacing, offset, cols, rows, cell size, caller.
"""
import argparse, struct, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gu import Game, ORIG  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('state'); ap.add_argument('--iso', default=ORIG); ap.add_argument('--taps', type=int, default=30)
    a = ap.parse_args()
    g = Game(a.iso, out='work/qa/glyphs', state=a.state)
    wins = {}

    def setg(g, r):
        k = (r['a0'], r['a1'])
        if k in wins: wins[k][0] += 1; return
        w = r['a0']
        xy = struct.unpack('<8h', g.rd(w, 16))
        cols, rows, cw, ch = struct.unpack('<4h', g.rd(w + 0x18, 8))
        wins[k] = [1, f'win {w:x} font {r["a1"]} x,y,w,h,spx,spy,offx,offy {xy} cols {cols} rows {rows} cell {cw}x{ch} '
                      f'caller {r["ra"] - g.load:x}']
    try:
        g.hook(0xA20E4, setg)
        for _ in range(a.taps): g.tap('circle', 6, 60)
        g.shot('end.png')
    finally:
        g.close()
    for n, s in wins.values(): print(n, s)


if __name__ == '__main__':
    main()
