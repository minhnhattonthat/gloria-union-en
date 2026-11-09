"""Shots older than their scene's last run (its memstick dir) in a warp tour root: left over from an earlier run of that scene
(warp.py does not clear a scene dir, and a rerun with other --shot-after delays leaves the old delay's files,
which tour.py sheets then prefers).

    python -X utf8 tools/tour_stale.py work/qa/final [--delete]
"""
import argparse
import os
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('root')
ap.add_argument('--delete', action='store_true')
a = ap.parse_args()
n = 0
for scene in sorted(p for p in Path(a.root).iterdir() if (p / 'memstick').exists()):
    t = (scene / 'memstick').stat().st_mtime - 5  # warp.py makes a fresh memstick when the scene's run starts
    old = [p for p in scene.glob('t*.png') if p.stat().st_mtime < t]
    if old:
        n += len(old)
        print(f'{scene.name}\t{len(old)} stale shots')
        if a.delete:
            for p in old:
                os.remove(p)
print(f'{n} stale shots{" deleted" if a.delete else ""}')
