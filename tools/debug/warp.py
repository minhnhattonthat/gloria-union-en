"""Cold boot to a scene from tools/debug/scenes.py and prove it (RAM or file assert plus a shot).

    python -X utf8 tools/debug/warp.py SCENE [--iso ISO] [--state-out F]
    python -X utf8 tools/debug/warp.py --all [--jobs 4] [--match stage_]      results in work/qa/warp/results.tsv

Each scene runs in its own process with a fresh memstick. Exit 1 if a scene was not reached.
"""
import argparse, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gu
from gu import psp
from scenes import AFTER_CHAR_SELECT, scenes

ROOT = 'work/qa/warp'


def reached(g, proof):
    kind, v = proof
    return v in g.files if kind == 'file' else g.mode() == v


def go(name, iso, state_out=None):
    kind, arg, proof = scenes()[name]
    g = gu.Game(iso, f'{ROOT}/{name}')
    g.watch_files()
    try:
        if kind == 'stage': g.warp(arg)
        if kind == 'boot': g.title()
        elif kind == 'mode':
            g.title(); g.wr32(gu.MODE, arg); g.tap('circle', 6, 120)
        else: g.new_game()
        if name in AFTER_CHAR_SELECT:
            g.until(lambda g: g.mode() == 20, 24000)
            g.run(300)   # mode 20 is set before the screen fades in and takes input
            for k in AFTER_CHAR_SELECT[name]: g.tap(k, 6, 90)
        ok = g.until(lambda g: reached(g, proof), 24000 if kind == 'stage' else 9000)
        g.run(180)   # past the fade-in, so the shot shows the scene
        g.shot('proof.png')
        if state_out: g.save_state(state_out)
        return ok and not psp.blank(f'{ROOT}/{name}/proof.png'), f'mode {g.mode()} frame {g.f}'
    finally:
        g.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scene', nargs='?'); ap.add_argument('--iso', default=gu.ORIG); ap.add_argument('--state-out')
    ap.add_argument('--all', action='store_true'); ap.add_argument('--jobs', type=int, default=4); ap.add_argument('--match', default='')
    a = ap.parse_args()
    if not a.all:
        try: ok, info = go(a.scene, a.iso, a.state_out)
        except Exception as e: ok, info = False, f'crash {e!r}'
        print('ok' if ok else 'FAIL', a.scene, info)
        sys.exit(0 if ok else 1)
    todo = [n for n in scenes() if a.match in n]
    running, results = [], []
    while todo or running:
        while todo and len(running) < a.jobs:
            n = todo.pop(0)
            running.append((n, subprocess.Popen([sys.executable, '-X', 'utf8', __file__, n, '--iso', a.iso], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)))
        for r in running[:]:
            if r[1].poll() is not None:
                line = r[1].stdout.read().strip().splitlines()[-1:] or ['FAIL no output']
                results.append((r[0], r[1].returncode, line[0])); running.remove(r); print(line[0], flush=True)
        time.sleep(0.5)
    with open(f'{ROOT}/results.tsv', 'w') as f:
        for n, c, l in sorted(results): f.write(f'{n}\t{c}\t{l}\n')
    bad = [r[0] for r in results if r[1]]
    print(f'{len(results) - len(bad)}/{len(results)} reached; failed: {bad}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
