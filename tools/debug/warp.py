"""Cold boot to a scene from tools/debug/scenes.py and prove it (RAM or file assert plus a shot).

    python -X utf8 tools/debug/warp.py SCENE [--iso ISO] [--state-out F]
    python -X utf8 tools/debug/warp.py --all [--jobs 4] [--match stage_]      results in work/qa/warp/results.tsv

Each scene runs in its own process with a fresh memstick. Exit 1 if a scene was not reached.
"""
import argparse, os, struct, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gu
from gu import psp
from scenes import KEYS, scenes

ROOT = 'work/qa/warp'
WAITS = {'stage': 24000, 'newgame': 24000, 'mode': 9000, 'fight': 6000}   # kinds that may need mashing to the proof; the rest are there
# stage scripts open before the fade in
SETTLE = {'stage': 480, 'game_over': 900, 'skill_cutin': 270}   # the defeat line types out; the skill's card and motto are up about 270 frames after it fires


def reached(g, proof):
    kind, v, *rest = (*proof, None)
    if kind == 'file': return v in g.files
    if kind == 'mode': return g.mode() == v
    if kind == 'fired': return g.fired
    if kind == 'byte': return g.rd(v, 1)[0] == rest[0]
    return struct.unpack('<h', g.rd(g.save() + 0x1A0, 2))[0] == v and rest[0] in g.files


def press(g, keys):
    for k in keys:
        if k.startswith('wait'): g.run(int(k.split()[1]))
        elif k == 'tutorials': g.wr(g.save(), b'\xff' * 32)   # save +0 bitset: the map menu's Tutorial list shows the set ids
        else: g.tap(k, 6, 90)


def go(name, iso, state_out=None):
    kind, arg, proof = scenes()[name]
    g = gu.Game(iso, f'{ROOT}/{name}')
    g.watch_files()
    try:
        if kind == 'outcome': g.warp(3)
        elif kind in ('stage', 'select', 'ready', 'field', 'fight', 'enemy', 'skill'): g.warp(arg)
        if kind == 'boot': g.title(); g.tap('circle', 6, 240)
        elif kind == 'title': g.title(); g.tap('circle', 6, 240)
        elif kind == 'cleared': g.title(); g.cleared(); g.tap('circle', 6, 240)
        elif kind == 'extra': g.title(); g.to_extra()
        elif kind == 'mode': g.title(); g.wr32(gu.MODE, arg); g.tap('circle', 6, 120)
        else: g.new_game()
        if kind == 'select': g.to_select()
        elif kind == 'ready': g.to_ready()
        elif kind in ('field', 'outcome', 'fight', 'enemy', 'skill'): g.to_field()
        if kind == 'fight': g.to_union()
        if kind in ('enemy', 'skill'):
            for _ in range(12):
                if not g.end_turn(lambda g: g.mode() == 34): break
        if kind == 'skill': g.skill()
        if kind == 'outcome': g.outcome(arg)
        press(g, KEYS.get(name, ()))
        ok = g.until(lambda g: reached(g, proof), WAITS[kind]) if kind in WAITS else g.until(lambda g: reached(g, proof), 300, None)
        g.run(SETTLE.get(name, SETTLE.get(kind, 180)))   # past the fade-in, so the shot shows the scene
        g.shot('proof.png')
        with open(f'{ROOT}/{name}/files.txt', 'w') as f: f.write(' '.join(map(str, g.files)))
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
