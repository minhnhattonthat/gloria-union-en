"""Text boxes: which window each entry is drawn in (from marker-tour logs) and the pixel budget of each window class.

    python -X utf8 tools/boxes.py scan [LOGDIR ...]   read <scene>/text.tsv from warp.py --text-log / talk.py --text-log
                                                     runs on a marker build; writes tbl/boxes.tsv; prints the classes
    python -X utf8 tools/boxes.py shots LOGDIR OUT    one shot per class from a --shots tour (OUT/index.tsv)
    python -X utf8 tools/boxes.py show               classes, budgets and how many entries each holds

A window class is (font, original columns, cell pitch, rows): the writer's window as the Japanese build sized it
(setSize gives 3x columns in our build, so columns are divided by 3). BUDGETS holds the measured limit per class:
px per line and lines, with the shot that measured it. An entry seen in several classes takes the smallest budget.
Entries never seen fall back to their file's default (DEFAULT), tagged 'guess'.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from insert import load, short  # noqa: E402

TSV = ROOT / 'tbl' / 'boxes.tsv'
CELL = {0: 8, 1: 20, 2: 14, 3: 24, 4: 12}

# class "font/cols/pitch/rows" -> (px per line, lines, how it was measured)
BUDGETS = {
    # dialogue window 0x10BE88 (story, tutorial talk): 4 rows of 288 px in our build (vwf.py), the 4th clears the
    # page arrow; work/qa/talk/stage_1_02_AP/p01.png (4 x 288 px stress lines inside the box)
    '1/16/18/4': (288, 4, 'measured: work/qa/talk/stage_1_02_AP/p01.png'),
    # fit sweep 2 (work/qa/fitsweep2, one shot per class in work/qa/gate2/NN_<class>.png): ruler read off the frame
    '1/10/18/1': (160, 1, 'measured: gate2/00 equip_tab, the "3 map" art covers the line past ~165 px'),
    '1/10/20/5': (190, 1, 'measured: gate2/01 title_option, On/Off starts ~195 px in; the ruler stopped at the 30-cell cap'),
    '1/15/17/6': (200, 6, 'measured: gate2/04 card_data, screen edge at ~202 px'),
    '2/6/14/9': (84, 9, 'measured: gate2/37 terrain list, 84 px ends before the first icon'),
}
DEFAULT = {'story': '1/16/18/4', 'common': '1/16/18/4'}


def klass(row):
    font = int(row['font']) % 16
    cw = int(row['cell_w']) or CELL.get(font, 20)
    return f'{font}/{int(row["cols"]) // 3}/{cw + int(row["spx"])}/{int(row["rows"])}'


def scan(dirs):
    ids = {}
    for sub in ('story', 'common', 'eboot'):
        for entries in load(sub).values():
            for e in entries:
                ids[short(e['id'])] = e['id']
    seen = defaultdict(set)
    where = defaultdict(set)
    for d in dirs:
        for p in Path(d).glob('*/text.tsv'):
            for row in csv.DictReader(p.open(encoding='utf8'), delimiter='\t', quoting=csv.QUOTE_NONE):
                m = re.match(r'\[([0-9a-z:]+)[\] ]', row['text'] or '')   # marker or stress.py head "[id px]"
                if not m or m.group(1) not in ids: continue
                k = klass(row)
                seen[ids[m.group(1)]].add(k)
                where[k].add(p.parent.name)
    TSV.parent.mkdir(exist_ok=True)
    with TSV.open('w', encoding='utf8', newline='\n') as f:
        f.write('id\tclasses\n')
        for i in sorted(seen):
            f.write(f'{i}\t{" ".join(sorted(seen[i]))}\n')
    c = Counter(k for ks in seen.values() for k in ks)
    for k, n in c.most_common():
        print(f'{k}\t{n} entries\t{BUDGETS.get(k, ("?",))[0]}\t{" ".join(sorted(where[k])[:4])}')
    print(len(seen), 'entries seen')


def shots(logdir, out):
    """One shot per class from a warp.py --text-log --shots tour: OUT/<n>_<class>.png (the first marked text of that
    class with a shot) and OUT/index.tsv (n, class, scene, shot, text), for reading budgets off the frame."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    got = {}
    for p in sorted(Path(logdir).glob('*/text.tsv')):
        for row in csv.DictReader(p.open(encoding='utf8'), delimiter='\t', quoting=csv.QUOTE_NONE):
            if not re.match(r'\[([0-9a-z:]+)[\] ]', row['text'] or '') or not row.get('shot'): continue
            if not (p.parent / row['shot']).exists(): continue   # the run died before the shot
            got.setdefault(klass(row), (p.parent.name, row['shot'], row['text'], row))
    with (out / 'index.tsv').open('w', encoding='utf8') as f:
        for n, (k, (scene, shot, text, row)) in enumerate(sorted(got.items())):
            name = f'{n:02d}_{k.replace("/", "-")}.png'
            (out / name).write_bytes((Path(logdir) / scene / shot).read_bytes())
            f.write(f'{n}\t{k}\t{scene}\t{shot}\tx{row["x"]} y{row["y"]} box{row["box_w"]}x{row["box_h"]}\t{text[:80]}\n')
    print(len(got), 'classes ->', out)


def classes():
    """{entry id: [class]} from tbl/boxes.tsv."""
    if not TSV.exists(): return {}
    rows = TSV.read_text('utf8').splitlines()[1:]
    return {r.split('\t')[0]: r.split('\t')[1].split() for r in rows}


def budget(entry, _cache={}):
    """-> (px per line, lines, class, measured?) or None when nothing is known."""
    if 'c' not in _cache: _cache['c'] = classes()
    ks = _cache['c'].get(entry['id'])
    if not ks:
        sub = {'s': 'story', 'c': 'common'}.get(entry['id'][0])
        ks = [DEFAULT[sub]] if sub else []
    best = None
    for k in ks:
        if k in BUDGETS:
            px, lines, how = BUDGETS[k]
            if best is None or px < best[0]: best = (px, lines, k, how.startswith('measured'))
    return best


if __name__ == '__main__':
    if sys.argv[1:2] == ['shots']:
        shots(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['scan']:
        scan(sys.argv[2:] or [ROOT / 'work/qa/warp', ROOT / 'work/qa/talk'])
    else:
        c = Counter(k for ks in classes().values() for k in ks)
        for k, n in c.most_common(): print(k, n, BUDGETS.get(k))
