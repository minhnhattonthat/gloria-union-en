"""Find which marked entries break a scene: build with only some id prefixes marked, warp, report.

    python -X utf8 tools/debug/markbisect.py SCENE GROUP [GROUP ...] [--en]   GROUP = comma-separated id prefixes, e.g. e:25,e:26
    --en: build the real English of those prefixes instead of markers

Each group gets its own marker build in work/qa/bis/<n>.iso and one warp; prints ok/FAIL per group.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    # --reuse: warp the g<n>.iso already built; --en: real English instead of markers
    scene, groups = sys.argv[1], [g for g in sys.argv[2:] if g not in ('--reuse', '--en')]
    mode = [] if '--en' in sys.argv else ['--marker']
    (ROOT / 'work/qa/bis').mkdir(parents=True, exist_ok=True)
    for n, grp in enumerate(groups):
        iso = ROOT / f'work/qa/bis/g{n}.iso'
        if '--reuse' not in sys.argv: subprocess.check_call([sys.executable, '-X', 'utf8', str(ROOT / 'build.py'), *mode, '--only', *grp.split(','), '-o', str(iso)],
                              stdout=subprocess.DEVNULL)
        r = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools/debug/warp.py'), scene, '--iso', str(iso)],
                           capture_output=True, text=True)
        print(grp, (r.stdout.strip().splitlines() or ['FAIL no output'])[-1], flush=True)


if __name__ == '__main__':
    main()
