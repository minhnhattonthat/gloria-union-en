"""Which name-table (0x2EE82C) entries are battle units: warp to a stage's first player turn and read every unit's
name index off the unit grid. Output: `stage<TAB>indices` lines, appended to OUT/units.tsv.

    python -X utf8 tools/debug/units.py STAGE [STAGE ...] [--iso ISO] [--out work/qa/units]

0xC61A0 (HUD/unit name): unit = word [s0 + 180 * side + 16 * slot + 0x10], name index = half [unit + 0x2A],
looked up by name(table 0x2EE82C, index) at 0x112038. The probe takes s0 from the first call there and reads the grid
(sides 0-15, slots 0-15) once the field is up; any other name lookups of the table are logged too (`i@caller`).
"""
import argparse, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gu
from scenes import KEYS

GETNAME = 0x112038   # vaddr: name(table, index)
GRID_CALL = 0xC61A0  # vaddr: lui before the HUD's name lookup; s0 = the unit grid's base
TABLE = 0x2EE82C     # vaddr: (name, 0, team name) records of 12 bytes


def stage_units(n, iso, out):
    g = gu.Game(iso, f'{out}/{n}')
    other, base = set(), []
    try:
        g.warp(n)
        g.new_game()
        g.hook(GETNAME, lambda g, r: other.add(f"{r['a1'] & 0xffff}@{r['ra'] - g.load:x}") if r['a0'] == g.load + TABLE else None)
        g.hook(GRID_CALL, lambda g, r: base.append(r['s0']) if not base else None)
        try:
            g.to_field()
        except RuntimeError as e:   # select screens some stages need other input for: keep what was looked up so far
            other.add(f'partial:{e}'.replace(' ', '_'))
            return [], sorted(other)
        for k in ('right', 'up', 'left', 'down'): g.tap(k, 6, 30)
        g.shot('field.png')
        for k in KEYS['menu_unit_list']: g.tap(k, 6, 90)   # the Unit List looks up every unit row's name
        g.run(200)
        for _ in range(12): g.tap('down', 6, 20)
        g.shot('units.png')
        units = set()
        if base:
            for side in range(16):
                for slot in range(16):
                    p = g.rd32(base[0] + 180 * side + 16 * slot + 0x10)
                    if 0x8800000 <= p < 0xA000000:
                        units.add(struct.unpack('<h', g.rd(p + 0x2A, 2))[0])
    finally:
        g.close()
    return sorted(units), sorted(other)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stages', nargs='+', type=int); ap.add_argument('--iso', default=gu.ORIG)
    ap.add_argument('--out', default='work/qa/units')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for n in a.stages:
        try:
            units, other = stage_units(n, a.iso, a.out)
            line = f'{n}\t' + ' '.join(map(str, units)) + '\t' + ' '.join(other)
        except Exception as e: line = f'{n}\tFAIL {e!r}'
        print(line, flush=True)
        with open(f'{a.out}/units.tsv', 'a') as f: f.write(line + '\n')


if __name__ == '__main__':
    main()
