"""Composite pages of many tour sheets, to read them with fewer image reads.

    python -X utf8 tools/tour_comp.py ROOT OUTDIR [--match story_] [--per 4]

Takes ROOT/*/sheet*.png (scene order), writes OUTDIR/comp_NNN.png (--per sheets each, 2 columns, full size) and
OUTDIR/comp.tsv (page, sheets) so a verdict on a page maps back to its sheets.
"""
import argparse, glob, os, subprocess, sys

from skill import SKILL


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root'); ap.add_argument('out'); ap.add_argument('--match', default=''); ap.add_argument('--per', type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    src = [p for p in sorted(glob.glob(os.path.join(a.root, '*', 'sheet*.png')))
           if a.match in os.path.basename(os.path.dirname(p))]
    rows = []
    for i in range(0, len(src), a.per):
        out = os.path.join(a.out, f'comp_{i // a.per:03d}.png')
        subprocess.run([sys.executable, '-X', 'utf8', os.path.join(SKILL, 'scripts', 'sheet.py'), *src[i:i + a.per],
                        '--cols', '2', '--div', '1', '--max', str(a.per), '--out', out], check=True, stdout=subprocess.DEVNULL)
        rows.append(f"{os.path.basename(out)}\t{' '.join(os.path.relpath(p, a.root) for p in src[i:i + a.per])}")
    with open(os.path.join(a.out, 'comp.tsv'), 'w', encoding='utf8') as f:
        f.write('\n'.join(rows) + '\n')
    print(f'{len(rows)} pages from {len(src)} sheets')


if __name__ == '__main__':
    main()
