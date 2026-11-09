"""QA tour helpers for a warp.py --all --text-log --shots run.

    python -X utf8 tools/tour.py sheets work/qa/tour [--match story_]   <scene>/sheet.png (+ sheet_2.png..) per scene
    python -X utf8 tools/tour.py jp work/qa/tour                        drawn texts that still hold Japanese; exit 1 if any

sheets: the scene's text shots (the latest delay's, t000_150.png.., if any) then proof.png, frames that barely change dropped
(sheet.py --changed), 12 to a page at half size. jp: every text.tsv row with kana or kanji, so a string the
build left Japanese (or a code-built one) shows without reading a sheet.
"""
import argparse, csv, glob, os, re, subprocess, sys

from skill import SKILL

JP = re.compile('[぀-ヿ一-鿿]')   # not full-width digits: the game's own number fields draw them


def shots(scene):
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(scene, 't[0-9][0-9][0-9]*.png')))
    late = [n for n in names if '_' in n]   # --shot-after 40,150: the later shot shows typed-out text; 40 is mid-typing
    names = late or names
    return [os.path.join(scene, n) for n in names] + [p for p in [os.path.join(scene, 'proof.png'), os.path.join(scene, 'end.png')] if os.path.exists(p)]


def sheets(root, match):
    for scene in sorted(glob.glob(os.path.join(root, '*', ''))):
        if match not in os.path.basename(os.path.dirname(scene)): continue
        for old in glob.glob(os.path.join(scene, 'sheet*.png')): os.remove(old)
        src = shots(scene)
        if not src: continue
        subprocess.run([sys.executable, '-X', 'utf8', os.path.join(SKILL, 'scripts', 'sheet.py'), *src, '--changed', '0.02',
                        '--max', '12', '--cols', '3', '--out', os.path.join(scene, 'sheet.png')], check=True, stdout=subprocess.DEVNULL)


def jp(root):
    n = 0
    for tsv in sorted(glob.glob(os.path.join(root, '*', 'text.tsv'))):
        with open(tsv, encoding='utf8') as f:
            for row in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
                if JP.search(row['text'] or ''):
                    n += 1; print(f"{os.path.basename(os.path.dirname(tsv))}\t{row['shot']}\t{row['text']}")
    print(f'{n} drawn texts with Japanese', file=sys.stderr)
    return 1 if n else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['sheets', 'jp']); ap.add_argument('root'); ap.add_argument('--match', default='')
    a = ap.parse_args()
    if a.cmd == 'sheets': sheets(a.root, a.match)
    else: sys.exit(jp(a.root))


if __name__ == '__main__':
    main()
