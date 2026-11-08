"""Text boxes: which window each entry is drawn in (from marker-tour logs) and the pixel budget of each window class.

    python -X utf8 tools/boxes.py scan [LOGDIR ...]   read <scene>/text.tsv from warp.py --text-log / talk.py --text-log
                                                     runs on a marker build; writes tbl/boxes.tsv; prints the classes
    python -X utf8 tools/boxes.py shots LOGDIR OUT    one shot per class from a --shots tour (OUT/index.tsv)
    python -X utf8 tools/boxes.py crops OUT [FIRST LAST]   each class shot cut to its window's rows, stacked, 2x
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
    # fit sweep 2 shots re-picked by boxes.py shots (work/qa/gate3/NN_<class>.png, sheets gate3/sheet/a-e.png)
    '1/20/20/22': (350, 22, 'measured: gate3/12 tutorial list, rulers stop at the 60-cell cap (~355 px); screen allows ~440'),
    '1/30/17/7': (245, 7, 'measured: gate3/14 object list, text from x 233, screen edge at +247'),
    '1/30/18/1': (460, 1, 'measured: gate3/15 character select bottom line, screen edge at ~465'),
    '1/30/20/1': (145, 1, 'measured: gate3/19 unit status Notice rows, screen edge at ~150'),
    '1/30/20/2': (600, 2, 'measured: gate3/20 CAUTION bar scrolls (ticker); 90-cell cap'),
    '1/30/20/6': (445, 6, 'measured: gate3/21 battle_result black page, text from x 32 to the screen edge'),
    '1/6/20/1': (125, 1, 'measured: gate3/23 battle_result win count field, x 350 to the screen edge'),
    '1/8/20/5': (150, 5, 'measured: gate3/24 battle_result unit name, next field at +158'),
    '2/10/14/7': (135, 7, 'measured: gate3/26 card list name, Pow. starts at +138'),
    '2/12/14/1': (168, 1, 'measured: gate3/27 VS screen skill tag, 168 px clear'),
    '2/12/14/5': (145, 5, 'measured: gate3/28 skill notice on the map, screen edge at ~150'),
    '2/13/14/1': (190, 1, 'measured: gate3/29 tactics card Info bar, screen edge at +197'),
    '2/15/14/2': (195, 2, 'measured: gate3/30 card data effect lines, screen edge at ~200'),
    '2/15/376/1': (480, 1, 'measured: gate3/31 card data top ticker (scrolls); 45-cell cap'),
    # fit sweep 3 (work/qa/fitsweep3, one shot per class in work/qa/gate4/)
    '1/12/20/2': (185, 2, 'measured: gate4/03 map menu right column, x 242 to the count field at ~435'),
    '3/15/22/1': (245, 1, 'measured: gate4/38 name tag, the plate ends near the 250 label; text past it draws on the map'),
    '3/20/22/1': (175, 1, 'measured: f4fix/menu_full_map/t024 header centred between the L and R arrows (~180 px); '
                          'a 40-char ruler drew stray glyphs at chars ~11 and ~33 (gate4/39): recheck real text in phase 7'),
    '4/20/12/10': (68, 1, 'measured: f4vwf/battle_result/t066 HUD unit name, the G/A/T gauges start at +75 (player); '
                          'enemy panel right-aligned: a 68 px name ends at the pips (work/qa/hud2_r.png)'),
    '4/20/12/6': (80, 1, 'measured: fm/step.png.01 full map unit placement lists, x 395 to the screen edge'),
    '1/30/19/1': (400, 1, 'measured: wincond/stage_3_07_B/proof.png win condition, x 70 to the screen edge'),
    '1/30/19/2': (425, 2, 'measured: wincond/stage_3_07_B/proof.png lose conditions, x 45 to the screen edge'),
    '1/30/19/3': (425, 3, 'measured: wincond/stage_3_07_B/proof.png lose conditions, x 45 to the screen edge'),
    '1/15/20/1': (200, 1, 'measured: fitslide2/battle_result/t033 unit name bar, right-aligned at x 211 (vwidth), bar can '
                          'reach the screen edge'),
    '1/20/20/1': (350, 1, 'measured: fitslide2/battle_result/t049 bark bubble x 67..~420; ruler cut by the 60-cell cap'),
    '2/5/14/1': (80, 1, 'measured: fitslide2/battle_result/t055 Factor values column, x 115 to the % art at ~200 (printf: '
                        'byte limits in tbl/fmtbuf.tsv apply first)'),
    '2/4/14/1': (56, 1, 'guess: fitslide2/battle_result/t055 Factor RESULT value; original width'),
    '2/16/14/5': (145, 5, 'measured: fitslide2/char_status/t009 Notice rows from x 327, screen edge at ~150'),
    '1/43/500/1': (860, 1, 'measured: fitslide2/card_data/t010 top ticker scrolls; 129-cell cap (~860 px of font 1)'),
    '1/21/20/3': (400, 3, 'measured: fitslide/battle_result/t024_150 black panel, ruler cut by the 63-cell cap at ~400'),
    '2/10/14/1': (140, 1, 'guess: card data skill name drawn faded behind the card art (fitslide2/card_data/t010); '
                          'original width'),
    '2/22/14/1': (290, 1, 'measured: gate3/33 card select bottom line 1 (skill effects, boxes.ROW_OF), x 12 to the '
                          'Total Move banner at ~305'),
    '2/22/14/2': (225, 2, 'measured: gate3/33 card select bottom, line 2 starts after its label and meets Total Move at ~227'),
    # EXTRA pages (work/qa/extra3/sheet/a.png, fit build with the %s byte limits): description panels start at x ~282
    # and run to the screen edge; list rows are byte-limited (tbl/fmtbuf.tsv), item descriptions wrap by build
    '2/30/14/25': (195, 3, 'measured: extra3/sheet/a.png scenario/card/music/drama/character panels, x 282 to the '
                           'screen edge'),
    '2/30/14/2': (195, 2, 'measured: s37/mp_sheet.png music panel shows lines 1-2 of 3 (audio drama the same, '
                          'scenario panel ends below line 2), boxes.ROW_OF'),
    '2/30/14/1': (185, 1, 'measured: s37/music_play.png list row ("NN " from x 62, the title meets the NOW PLAYING '
                          'panel at ~x 270; a \\n breaks onto the next row) and the title bar over the panel (~185 px); '
                          'titles of the 2/30/14/2 tables'),
    # session 7: stage_clear from work/states/stage_clear_fit.ppst + step waits; popups from warp.py --state-at
    '1/11/20/2': (220, 1, 'measured: sc6/z.png War record rows from x ~190 under the label art, its right edge ~410 '
                          '(= 11 cols x 20); one entry per row'),
    '1/20/20/2': (235, 1, 'measured: sc6/z.png morale bonus line in the yellow bar, x 28 to the morale icon at ~265'),
    '1/15/20/2': (185, 2, 'measured: treas3/za.png treasure bubble (card name, code 0x10ec80 at x 284 y 96): text from x '
                          '285, the bubble grows past the screen edge; scenario desc bar (scensel2/z6.png) x 197, row 2 '
                          'stops at the difficulty stars ~405'),
    '1/15/20/3': (185, 3, 'guess: same window as 1/15/20/2 (code 0x10f570, x 284 y 96), item drop in battle_result; '
                          'never seen on screen'),
    '1/18/20/1': (180, 1, 'guess: "this scenario?" (e:2bc632) never seen drawn; the same question is a PTX at top left '
                          '(id 2426/2427, scensel2/z7.png), 180 px before the FAME bar'),
}
# entries of a fmtbuf.tsv group (matched in its note) shown in a narrower field than their window class says
GROUPS = {'item name': (134, 1, 'measured: itemdesc2/z.png EXTRA item page name, x 298 to the dotted strip at ~432')}
# a line also stops at 3 x the original columns (setSize), whatever its width: see cell_cap()
DEFAULT = {'story': '1/16/18/4', 'common': '1/16/18/4'}
# EBOOT entries never seen on a tour: a pointer table (w: slots no more than 0x40 apart, table_classes()) with a seen
# entry lends its classes to the rest; tables with none seen take a class by what they hold (slot address ranges,
# first slot inclusive), all 'guess'. Groups and why: docs/re/windows.md.
SOURCE = [
    (0x1f1000, 0x247fff, '1/20/20/1', 'battle barks and skill mottos: bark bubble (seen tables of both kinds draw there)'),
    (0x2bb824, 0x2bb8ec, '1/21/20/3', 'skill cannot be used: battle message panel'),
    (0x2c5c20, 0x2c6074, '1/30/18/1', 'place names: like the map overview table next to it'),
    (0x2c8744, 0x2c8780, '1/21/20/3', 'morale messages'), (0x2cb13c, 0x2cb178, '1/21/20/3', 'morale messages'),
    (0x2caa5c, 0x2caa7c, '1/21/20/3', 'morale messages'),
    (0x2ca560, 0x2ca650, '2/15/14/2', 'item/card conditions: card data effect lines'),
    (0x2cb8dc, 0x2cb9c0, '2/10/14/7', 'unit class names: card list name column'),
    (0x2cc710, 0x2cc8c0, '2/10/14/7', 'unit class names: card list name column'),
    (0x25e1d4, 0x25e34c, '2/30/14/25', 'EXTRA music titles (28-byte rows, tbl/fmtbuf.tsv)'),
    (0x2f6ca4, 0x2f6d1c, '2/30/14/25', 'EXTRA quotes'), (0x2f7eec, 0x2f7fec, '2/30/14/25', 'EXTRA card conditions'),
    (0x2f8e14, 0x2f8e1c, '1/21/20/3', 'EXTRA contents added notice'),
    (0x2f68a8, 0x2f68f4, '1/30/18/1', 'character catchphrases: character select bottom line'),
    (0x2f3960, 0x2f3d40, '1/30/20/6', 'stage outcome and recap lines: battle_result black page'),
    (0x2edd04, 0x2eddac, 'sys', 'PSP system message dialog (savedata/install): firmware font, it wraps itself'),
    (0x2eda40, 0x2edc8c, 'sys', 'PSP system message dialog: same %s / ALLKB / [0A] savedata messages as above'),
    (0x2f9570, 0x2f95e8, 'sys', 'PSP system message dialog (savedata/install)'),
]
GUESS = {'sys': (400, 6, 'guess: PSP system dialog wraps its own text; [0A] are its line breaks')}
I_DEFAULT = ('1/21/20/3', 'single strings built in code (i: slots): messages and menu rows')


def cell_cap(k):
    """Characters a line of class k can hold at most: setSize gives 3 x the original columns."""
    return 3 * int(k.split('/')[1])


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
    from stress import box_px
    got = {}
    for p in sorted(Path(logdir).glob('*/text.tsv')):
        for row in csv.DictReader(p.open(encoding='utf8'), delimiter='\t', quoting=csv.QUOTE_NONE):
            m = re.match(r'\[([0-9a-z:]+)(?: (\d+))?[\] ]', row['text'] or '')
            if not m or not row.get('shot'): continue
            if not (p.parent / row['shot']).exists(): continue   # the run died before the shot
            # a fit ruler is laid out for one window's font and width ("[id PX]"); in an entry's other windows its
            # labels sit at the wrong x, so prefer a row the ruler was made for
            rank = 0 if m.group(2) and int(m.group(2)) == box_px(row) else 1
            k = klass(row)
            if k not in got or rank < got[k][0]:
                got[k] = (rank, p.parent.name, row['shot'], row['text'], row)
    with (out / 'index.tsv').open('w', encoding='utf8') as f:
        for n, (k, (rank, scene, shot, text, row)) in enumerate(sorted(got.items())):
            name = f'{n:02d}_{k.replace("/", "-")}.png'
            (out / name).write_bytes((Path(logdir) / scene / shot).read_bytes())
            f.write(f'{n}\t{k}\t{scene}\t{shot}\tx{row["x"]} y{row["y"]} box{row["box_w"]}x{row["box_h"]}\t'
                    f'{"ruler" if rank == 0 else "ruler made for another window"}\t{text[:80]}\n')
    print(len(got), 'classes ->', out)


def crops(out, first=0, last=99, zoom=2):
    """OUT/crops_<first>.png: each class shot of OUT/index.tsv cut to its window's row band (full screen width, the
    box's y range + 6 px), zoomed and stacked with its label, to read many budgets from one image."""
    from PIL import Image, ImageDraw
    out = Path(out)
    rows = [r.split('\t') for r in (out / 'index.tsv').read_text('utf8').splitlines()]
    tiles = []
    for r in rows:
        n = int(r[0])
        if not first <= n <= last: continue
        x, y, box = r[4].split()
        y = int(y[1:]); h = int(box.split('x')[1])
        y0, y1 = max(0, y - 6), min(272, y + max(h, 12) + 6)
        im = Image.open(next(out.glob(f'{n:02d}_*.png'))).convert('RGB').crop((0, y0, 480, y1))
        im = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
        lab = Image.new('RGB', (im.width, 14), (0, 0, 0))
        ImageDraw.Draw(lab).text((2, 1), f'{n} {r[1]} {r[2]} {r[4]} {r[5][:30]}', fill=(255, 255, 0))
        tiles += [lab, im]
    sheet = Image.new('RGB', (480 * zoom, sum(t.height for t in tiles)), (40, 40, 40))
    yy = 0
    for t in tiles:
        sheet.paste(t, (0, yy)); yy += t.height
    p = out / f'crops_{first:02d}.png'
    sheet.save(p)
    print(p, sheet.size)


def classes():
    """{entry id: [class]} from tbl/boxes.tsv."""
    if not TSV.exists(): return {}
    rows = TSV.read_text('utf8').splitlines()[1:]
    return {r.split('\t')[0]: r.split('\t')[1].split() for r in rows}


# slot addresses where one pointer table ends and the next starts with no gap between them
SPLITS = {0x2ef27c: 'unit name records (0x2ee82c, 12 bytes, HUD) end; a 4-byte place list follows (fight screen '
                    'place bar, e:2816e4 seen in 1/15/20/1)',
          0x2eda40: "the game's own storage messages (window) end; PSP system dialog messages follow (SOURCE 'sys')",
          0x2c96a8: 'card character lines (■name, seen in the 1-row card data ticker 2/15/376/1) end; card effect '
                    'detail lines (■Power=..., card data effect lines 2/15/14/2) follow',
          0x2ca150: 'card skill effects (seen only in the card select bottom 2/22/14/2) end; skill use conditions '
                    '(Info bar 2/13/14/1, e:25704c) follow'}


def table_classes(seen):
    """{eboot entry id: [class]} for unseen entries in a pointer table (w: slots <= 0x40 apart) with seen entries."""
    rows = sorted((int(e['slots'][0][2:], 16), e['id']) for es in load('eboot').values() for e in es
                  if e.get('slots') and e['slots'][0].startswith('w:'))
    out, run = {}, []
    for i, r in enumerate(rows + [(1 << 40, None)]):
        if run and (r[0] - run[-1][0] > 0x40 or r[0] in SPLITS):
            ks = sorted({k for _, j in run for k in seen.get(j, [])})
            if ks: out.update((j, ks) for _, j in run if j not in seen)
            run = []
        run.append(r)
    return out


ROWS_FROM_TEXT = ('1/30/19/',)
# (first slot, last slot, class seen, class meant): a table drawn on one row of a shared window
ROW_OF = [(0x2ca000, 0x2ca14c, '2/22/14/2', '2/22/14/1'),   # skill effects: line 1 of the card select bottom
          # EXTRA scenario (0x2f6d6c, 12-byte rows) and music + audio drama (0x2f8090, 16-byte rows) descriptions:
          # the same window as the 3-line card/character panels, but those pages show only 2 lines
          (0x2f6d6c, 0x2f6fff, '2/30/14/25', '2/30/14/2'), (0x2f8090, 0x2f854f, '2/30/14/25', '2/30/14/2'),
          # ...and their titles (row +4 / +8): one list row ("%02d %s") and the one-line title bar
          (0x2f6d6c, 0x2f6fff, '2/30/14/2', '2/30/14/1', 0xC, 4), (0x2f8090, 0x2f854f, '2/30/14/2', '2/30/14/1', 0x10, 8)]
NAMES = (0x2ee82c, 0x2ef27c)   # unit records (full name, short name or 0, team name or 0), 12 bytes; no aliases
HUD, TEAM = '4/20/12/10', '4/20/12/6'


def record_classes(entry, _c={}):
    """Classes from the unit record fields an entry's slots fill: the battle HUD shows the short name, or the full
    name when the record has none (reader 0xf38e4 -> 0x112080); full map unit lists show team names."""
    if 'w' not in _c:
        _c['w'] = {int(s[2:], 16) for es in load('eboot').values() for e in es for s in e.get('slots') or []
                   if s.startswith('w:')}
    out = set()
    for s in entry.get('slots') or []:
        a = int(s[2:], 16) if s.startswith('w:') else 0
        if not NAMES[0] <= a < NAMES[1]: continue
        off = (a - NAMES[0]) % 12
        if off == 4 or (off == 0 and a + 4 not in _c['w']): out.add(HUD)
        if off == 8: out.add(TEAM)
    return out


def source_class(entry):
    """(class, note) for an EBOOT entry never seen and in no seen table, from SOURCE / I_DEFAULT."""
    s = (entry.get('slots') or ['?'])[0]
    if s.startswith('w:'):
        a = int(s[2:], 16)
        for lo, hi, k, note in SOURCE:
            if lo <= a <= hi: return k, note
    if s.startswith('i:'): return I_DEFAULT
    return None


def budget(entry, _cache={}):
    """-> (px per line, lines, class, measured?) or None when nothing is known. measured? is False for an entry never
    seen on a tour (table or source class) or a class whose budget is a guess."""
    if 'c' not in _cache:
        _cache['c'] = classes()
        _cache['t'] = table_classes(_cache['c'])
    ks = _cache['c'].get(entry['id'])
    seen = bool(ks) or entry['id'][0] in 'sc'   # story and common text all goes to the dialogue window
    if not ks:
        sub = {'s': 'story', 'c': 'common'}.get(entry['id'][0])
        ks = [DEFAULT[sub]] if sub else _cache['t'].get(entry['id'])
    if not ks and entry['id'].startswith('e:'):
        sc = source_class(entry)
        if sc and sc[0] in GUESS: return (*GUESS[sc[0]][:2], sc[0], False)
        ks = [sc[0]] if sc else []
    rc = record_classes(entry) if entry['id'].startswith('e:') else set()
    if rc or any(k in (HUD, TEAM) for k in ks or []) and not seen:
        # unit record fields: HUD and full map classes by field (record_classes), not lent by the table run
        ks = sorted({k for k in ks or [] if seen or k not in (HUD, TEAM)} | rc)
    if 'g' not in _cache:
        rows = [r.split('\t') for r in (ROOT / 'tbl/fmtbuf.tsv').read_text('utf8').splitlines()[1:]]
        _cache['g'] = {r[0]: g for r in rows for g in GROUPS if g in r[4]}
    # windows sized by the text's own line count (win/lose conditions: rows 1-3 of the same window in the logs)
    n = entry.get('jp', '').count('\n') + entry.get('jp', '').count('[0A]') + 1
    ks = [k.rsplit('/', 1)[0] + f'/{n}' if k.startswith(ROWS_FROM_TEXT) and k.rsplit('/', 1)[0] + f'/{n}' in BUDGETS
          else k for k in ks]
    slots = [int(s[2:], 16) for s in entry.get('slots') or [] if s.startswith('w:')]
    for lo, hi, k0, k1, *every in ROW_OF:   # every: (stride, offset) of the slots meant, else the whole range
        if any(lo <= a <= hi and (not every or (a - lo) % every[0] == every[1]) for a in slots):
            ks = [k1 if k == k0 else k for k in ks]
    cand = [(BUDGETS[k], k) for k in ks if k in BUDGETS]
    if entry['id'] in _cache['g']: cand.append((GROUPS[_cache['g'][entry['id']]], _cache['g'][entry['id']]))
    best = None
    for (px, lines, how), k in cand:
        if best is None or px < best[0]:
            best = (px, lines, k, how.startswith('measured') and (seen or k in GROUPS or k in rc))
    if best:   # the fewest lines of any window it is drawn in (a 1-line tag and a 5-line list: 1 line)
        best = (best[0], min(c[0][1] for c in cand), *best[2:])
    return best


if __name__ == '__main__':
    if sys.argv[1:2] == ['shots']:
        shots(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['crops']:
        crops(sys.argv[2], *map(int, sys.argv[3:5]))
    elif sys.argv[1:2] == ['scan']:
        scan(sys.argv[2:] or [ROOT / 'work/qa/warp', ROOT / 'work/qa/talk'])
    else:
        c = Counter(k for ks in classes().values() for k in ks)
        for k, n in c.most_common(): print(k, n, BUDGETS.get(k))
