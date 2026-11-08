"""Press keys from a saved state, print the mode after each, leave a shot and the new state: for finding routes.

    python -X utf8 tools/debug/step.py work/states/a.ppst circle down "wait 300" --out work/states/b.ppst --shot work/qa/step.png
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gu

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('state'); ap.add_argument('keys', nargs='*'); ap.add_argument('--out'); ap.add_argument('--shot', default='work/qa/step/shot.png')
ap.add_argument('--gap', type=int, default=60); ap.add_argument('--each', action='store_true', help='also shot each step: <shot>.N.png')
ap.add_argument('--iso', default=gu.ORIG, help='the build the state was saved on (files load from it)')
a = ap.parse_args()
d = os.path.dirname(a.shot)
g = gu.Game(a.iso, d, a.state)
g.watch_files()
g.run(2)
for i, k in enumerate(a.keys):
    if k.startswith('wait'): g.run(int(k.split()[1]))
    else: g.tap(k, 6, a.gap)
    print(k, 'mode', g.mode(), 'files', g.files, flush=True)
    g.files.clear()
    if a.each: g.shot(f'{os.path.basename(a.shot)}.{i:02}.png')
g.shot(os.path.basename(a.shot))
if a.out: g.save_state(a.out)
g.close()
