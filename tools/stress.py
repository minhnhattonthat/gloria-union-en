"""Width-gate stress text: lines filled to a pixel width with vwf.line_px, plus the glyph torture line.

    python -X utf8 tools/stress.py ID PX LINES [--font 1] [--ruler]   prints ID=TEXT for build.py --qa
    python -X utf8 tools/stress.py --torture ID                        all printable ASCII and double spaces

A ruler line ends in digits counting characters, so a shot shows where the box cuts it.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vwf  # noqa: E402

WORDS = 'Ishto Pinger Luluu sail toward the Sea King Temple while Ellysia waits on the dock with Minnesota and friends'.split()


def fill(px, font, head=''):
    s, i = head, 0
    while True:
        w = WORDS[i % len(WORDS)]
        t = (s + ' ' + w) if s else w
        if vwf.line_px(t, font) > px: break
        s, i = t, i + 1
    while vwf.line_px(s + '.', font) <= px: s += '.'
    return s


def torture():
    asc = ''.join(chr(c) for c in range(0x21, 0x7F))
    return '\n'.join([asc[:32], asc[32:64], asc[64:] + '  A  B', 'Wm  iI  1l|  "Hi!"  (Lv 99)'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('id'); ap.add_argument('px', nargs='?', type=int); ap.add_argument('lines', nargs='?', type=int, default=1)
    ap.add_argument('--font', type=int, default=1); ap.add_argument('--torture', action='store_true')
    a = ap.parse_args()
    if a.torture:
        print(f'{a.id}={torture()}'.replace('\n', '\\n'))
    else:
        lines = [fill(a.px, a.font, f'[{a.px}px {i + 1}]') for i in range(a.lines)]
        print(f'{a.id}=' + '\\n'.join(lines))
