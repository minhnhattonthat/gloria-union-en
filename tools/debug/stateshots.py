"""Load a PPSSPP state and shoot every N frames (emu.py --state-in times out on these states).

    python -X utf8 tools/debug/stateshots.py STATE --iso ISO --out DIR [--frames 900] [--every 15]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from gu import Game  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('state'); ap.add_argument('--iso', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--frames', type=int, default=900); ap.add_argument('--every', type=int, default=15)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
g = Game(a.iso, a.out, os.path.abspath(a.state))
try:
    for f in range(a.every, a.frames + 1, a.every):
        g.run(a.every)
        g.shot(f'f{f:06d}.png')
finally:
    g.close()
print('ok', a.out)
