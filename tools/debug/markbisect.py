"""Find which marked entries break a scene: build with only some id prefixes marked, warp, report.

    python -X utf8 tools/debug/markbisect.py SCENE GROUP [GROUP ...]     GROUP = comma-separated id prefixes, e.g. e:25,e:26

Each group gets its own marker build in work/qa/bis/<n>.iso and one warp; prints ok/FAIL per group.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    scene, groups = sys.argv[1], [g for g in sys.argv[2:] if g != '--reuse']   # --reuse: warp the g<n>.iso already built
    (ROOT / 'work/qa/bis').mkdir(parents=True, exist_ok=True)
    for n, grp in enumerate(groups):
        iso = ROOT / f'work/qa/bis/g{n}.iso'
        if '--reuse' not in sys.argv: subprocess.check_call([sys.executable, '-X', 'utf8', str(ROOT / 'build.py'), '--marker', '--only', *grp.split(','), '-o', str(iso)],
                              stdout=subprocess.DEVNULL)
        r = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools/debug/warp.py'), scene, '--iso', str(iso)],
                           capture_output=True, text=True)
        print(grp, (r.stdout.strip().splitlines() or ['FAIL no output'])[-1], flush=True)


if __name__ == '__main__':
    main()
