"""Per scene, the drawn texts (and their box geometry) of a new tour vs an already-read one.

    python -X utf8 tools/tour_diff.py work/qa/final work/qa/tour [--show SCENE]

Prints "same|changed|new SCENE" per scene of the new root: same = every (text, x, y, box) drawn is the same set.
"""
import argparse
import csv
from pathlib import Path


def drawn(p):
    if not p.exists():
        return None
    with p.open(encoding='utf8', newline='') as f:
        return {(r['text'], r['x'], r['y'], r['box_w'], r['box_h']) for r in csv.DictReader(f, delimiter='\t')}


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('new'); ap.add_argument('old'); ap.add_argument('--show')
a = ap.parse_args()
for d in sorted(p for p in Path(a.new).iterdir() if p.is_dir()):
    n, o = drawn(d / 'text.tsv'), drawn(Path(a.old) / d.name / 'text.tsv')
    if n is None:
        continue
    print('new' if o is None else 'same' if n == o else 'changed', d.name, '' if o is None else f'-{len(o - n)} +{len(n - o)}')
    if a.show == d.name and o is not None:
        for t in sorted(o - n): print('  -', t)
        for t in sorted(n - o): print('  +', t)
