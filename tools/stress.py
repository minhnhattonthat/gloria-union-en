"""Width-gate stress text: lines filled to a pixel width with vwf.line_px, plus the glyph torture line.

    python -X utf8 tools/stress.py ID PX LINES [--font 1] [--ruler]   prints ID=TEXT for build.py --qa
    python -X utf8 tools/stress.py --torture ID                        all printable ASCII and double spaces
    python -X utf8 tools/stress.py OUT.tsv --fit LOGDIR..               every toured entry filled to its box (build.py --qa-file)

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


def ruler(px, font, head=''):
    """HEAD, then dots with a label whose last digit ends at each 50 px from the line start, up to PX."""
    s, k = head, 1
    while k * 50 <= px:
        lab = str(k * 50)
        while vwf.line_px(s + '.' + lab, font) <= k * 50: s += '.'
        if vwf.line_px(s + lab, font) <= min(px, k * 50 + 2): s += lab   # a label the head already passed is left out
        k += 1
    while vwf.line_px(s + '.', font) <= px: s += '.'
    return s


def fit(logdirs):
    """ID<tab>TEXT lines: every marked entry seen in the tour logs, each line filled to its window's box width
    (box_w; cols x pitch when box_w is under 40 px), as many lines as the original, at most the window's rows.
    Entries with printf codes keep their marker (args must match)."""
    import csv, re
    from insert import FMT, load, short
    ids = {short(e['id']): e for sub in ('story', 'common', 'eboot') for es in load(sub).values() for e in es}
    out = {}
    for d in logdirs:
        for p in Path(d).glob('*/text.tsv'):
            for r in csv.DictReader(p.open(encoding='utf8'), delimiter='\t', quoting=csv.QUOTE_NONE):
                m = re.match(r'\[([0-9a-z:]+)[\] ]', r['text'] or '')
                e = m and ids.get(m.group(1))
                if not e or FMT.search(e['jp']) or '[0A]' in e['jp']: continue
                font = int(r['font']) % 16
                px = int(r['box_w'])
                if px < 40: px = int(r['cols']) // 3 * (int(r['cell_w']) or 20) + int(r['spx']) * (int(r['cols']) // 3)
                n = max(1, min(e['jp'].count('\n') + 1, int(r['rows'])))
                if e['id'] in out and out[e['id']][0] <= px: continue
                out[e['id']] = (px, '\\n'.join(ruler(px, font, f'[{m.group(1)} {px}]' if i == 0 else f'{i + 1}') for i in range(n)))
    return '\n'.join(f'{k}\t{v[1]}' for k, v in sorted(out.items())) + '\n'


def torture():
    asc = ''.join(chr(c) for c in range(0x21, 0x7F))
    return '\n'.join([asc[:32], asc[32:64], asc[64:] + '  A  B', 'Wm  iI  1l|  "Hi!"  (Lv 99)'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('id'); ap.add_argument('px', nargs='?', type=int); ap.add_argument('lines', nargs='?', type=int, default=1)
    ap.add_argument('--font', type=int, default=1); ap.add_argument('--torture', action='store_true')
    ap.add_argument('--fit', nargs='+', metavar='LOGDIR', help='id = output TSV path; fill every entry seen in LOGDIRs to its box')
    a = ap.parse_args()
    if a.fit:
        Path(a.id).write_text(fit(a.fit), 'utf8')
    elif a.torture:
        print(f'{a.id}={torture()}'.replace('\n', '\\n'))
    else:
        lines = [fill(a.px, a.font, f'[{a.px}px {i + 1}]') for i in range(a.lines)]
        print(f'{a.id}=' + '\\n'.join(lines))
