"""Cold boot to a scene from tools/debug/scenes.py and prove it (RAM or file assert plus a shot).

    python -X utf8 tools/debug/warp.py SCENE [--iso ISO] [--state-out F]
    python -X utf8 tools/debug/warp.py --all [--jobs 4] [--match stage_]      results in work/qa/warp/results.tsv
    --text-log [--shots]: log every text drawn (<scene>/text.tsv), with a shot of each; --root DIR: output folder

Each scene runs in its own process with a fresh memstick. Exit 1 if a scene was not reached.
"""
import argparse, os, re, struct, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gu
from gu import psp
from scenes import KEYS, scenes

ROOT = 'work/qa/warp'
BANNER_CALL, BANNER_STAGE = 0x11A0BC, 3   # op 0x4A handler's call to the banner loader (a1 = banner number)
WAITS = {'stage': 24000, 'newgame': 24000, 'mode': 9000, 'fight': 6000, 'banner': 24000}   # kinds that may need mashing to the proof; the rest are there
# stage scripts open before the fade in
SHOT_AFTERS = [40]   # frames from a text's first draw to its shots (log_text shots): past window fade-ins; --shot-after
STORY_GAP, STORY_LIMIT = 200, 90000   # story kind: frames between Circle taps, frame budget
STATE_AT = [None, None]   # --state-at TEXT F: (text to wait for, state file)
SETTLE = {'stage': 480, 'game_over': 900, 'skill_cutin': 270}   # the defeat line types out; the skill's card and motto are up about 270 frames after it fires


def reached(g, proof):
    kind, v, *rest = (*proof, None)
    if kind == 'file': return v in g.files
    if kind == 'mode': return g.mode() == v
    if kind == 'fired': return g.fired
    if kind == 'byte': return g.rd(v, 1)[0] == rest[0]
    if kind == 'story': return g.mode() in (15, 20, 39, 41) or len(set(g.loaded)) > 1   # select, field, credits, next stage
    return struct.unpack('<h', g.rd(g.save() + 0x1A0, 2))[0] == v and rest[0] in g.files


def press(g, keys):
    for k in keys:
        if k.startswith('wait'): g.run(int(k.split()[1]))
        elif k == 'tutorials': g.wr(g.save(), b'\xff' * 32)   # save +0 bitset: the map menu's Tutorial list shows the set ids
        else: g.tap(k, 6, 90)


def log_text(g, path, shots=False):
    """Hook the text writer 0xA222C: one TSV row per (window, font, text) drawn, with the window's geometry
    (docs/re/text.md, Text renderer). A typewriter window (t3 = 1) is logged at its first character.
    shots: a shot SHOT_AFTERS[0] frames after a text is first drawn (t000.png, ...; shared by texts drawn meanwhile;
    t000_<N>.png for each later delay N),
    named in the row's last column, so every window met on a tour has a frame showing it (width gate)."""
    seen = set()
    f = open(path, 'w', encoding='utf8')
    f.write('win\tfont\tcol\trow\tx\ty\tbox_w\tbox_h\tspx\toffx\tcols\trows\tcell_w\tcell_h\ttext\tshot\n')
    n = [0]

    def shot_name(g):
        if not shots: return ''
        if g.later: return g.later[0][2]
        name = f't{n[0]:03d}.png'; n[0] += 1
        for i, after in enumerate(SHOT_AFTERS):   # later shots: t000_<frames>.png, for windows that slide in
            nm = name if i == 0 else name.replace('.png', f'_{after}.png')
            g.later.append((g.frame() + after, lambda g, nm=nm: g.shot(nm), name))
        return name

    def hit(g, r):
        if r['t3'] and (r['a1'] & 0xFFFF or r['a2'] & 0xFFFF): return
        try:
            raw = g.rd(r['t1'], 164)
            if raw[0] == 2: raw = raw[4:]   # 02 00 <u16 voice id> tag before a message (docs/re/text.md)
            raw = raw.split(b'\0')[0]
            key = (r['a0'], r['t0'], raw)
            if key in seen: return
            geo = struct.unpack('<8h', g.rd(r['a0'], 16))
            cols, rows, cw, ch = struct.unpack('<4h', g.rd(r['a0'] + 0x18, 8))
        except RuntimeError: return   # a pointer near the end of RAM
        seen.add(key)
        t = raw.decode('cp932', 'replace').replace('\x01', '\\n').replace('\t', ' ').replace('\n', '[0A]')
        s16 = lambda v: struct.unpack('<h', struct.pack('<H', v & 0xFFFF))[0]
        f.write(f'{r["a0"]:x}\t{r["t0"]}\t{s16(r["a1"])}\t{s16(r["a2"])}\t{geo[0]}\t{geo[1]}\t{geo[2]}\t{geo[3]}\t{geo[4]}\t{geo[6]}\t'
                f'{cols}\t{rows}\t{cw}\t{ch}\t{t}\t{shot_name(g)}\n')
        f.flush()
        if STATE_AT[0] and STATE_AT[0] in t:   # --state-at: a state one frame after this text first draws
            p, STATE_AT[0] = STATE_AT[1], None
            g.later.append((g.frame() + 1, lambda g: g.save_state(p), ''))
    g.hook(0xA222C, hit)
    return f


def go(name, iso, state_out=None, text_log=False):
    kind, arg, proof = scenes()[name]
    g = gu.Game(iso, f'{ROOT}/{name}')
    g.watch_files()
    if text_log: log_text(g, f'{ROOT}/{name}/text.tsv', text_log == 'shots')
    try:
        if kind == 'outcome': g.warp(3)
        elif kind in ('stage', 'select', 'ready', 'field', 'fight', 'enemy', 'skill', 'story'): g.warp(arg)
        elif kind == 'banner': g.warp(BANNER_STAGE)
        if kind == 'boot': g.title(); g.tap('circle', 6, 240)
        elif kind == 'title': g.title(); g.tap('circle', 6, 240)
        elif kind == 'cleared': g.title(); g.cleared(); g.tap('circle', 6, 240)
        elif kind == 'extra': g.title(); g.to_extra()
        elif kind == 'mode': g.title(); g.wr32(gu.MODE, arg); g.tap('circle', 6, 120)
        else: g.new_game()
        if kind == 'banner':   # op 0x4A shows event banner n (file 1945 + n): swap the stage's first one for ARG
            def banner(g, r):
                g.setreg('a1', arg)
                if not getattr(g, 'banner_shot', False):   # the first one; it slides in by +30 and out after +70
                    g.banner_shot = True
                    g.later.append((g.frame() + 50, lambda g: g.shot('proof.png'), ''))
            g.hook(BANNER_CALL, banner)
            g.to_ready(); g.tap('circle', 6, 60)
        if kind == 'story':   # slow taps: each page types out in full before the next press (shots at --shot-after)
            end = g.f + STORY_LIMIT
            while g.f < end and not reached(g, proof): g.tap('circle', 6, STORY_GAP)
        if kind == 'select': g.to_select()
        elif kind == 'ready': g.to_ready()
        elif kind in ('field', 'outcome', 'fight', 'enemy', 'skill'): g.to_field()
        if kind == 'fight': g.to_union()
        if kind in ('enemy', 'skill'):
            for _ in range(12):
                if not g.end_turn(lambda g: g.mode() == 34): break
        if kind == 'skill':   # the first fight can be one where Square never fires (an enemy card skill): try later ones
            for _ in range(6):
                if g.skill(): break
                g.until(lambda g: g.mode() != 34, 6000, 'circle')
                for _ in range(12):
                    if not g.end_turn(lambda g: g.mode() == 34): break
        if kind == 'outcome': g.outcome(arg)
        press(g, KEYS.get(name, ()))
        ok = g.until(lambda g: reached(g, proof), WAITS[kind]) if kind in WAITS else g.until(lambda g: reached(g, proof), 300, None)
        g.run(SETTLE.get(name, SETTLE.get(kind, 180)))   # past the fade-in, so the shot shows the scene
        g.shot('end.png' if kind == 'banner' else 'proof.png')   # banner: the run ends on Tactics Card select (team banner)
        with open(f'{ROOT}/{name}/files.txt', 'w') as f: f.write(' '.join(map(str, g.files)))
        if state_out: g.save_state(state_out)
        return ok and not psp.blank(f'{ROOT}/{name}/proof.png'), f'mode {g.mode()} frame {g.f}'
    finally:
        g.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scene', nargs='?'); ap.add_argument('--iso', default=gu.ORIG); ap.add_argument('--state-out')
    ap.add_argument('--text-log', action='store_true', help='log every text the writer draws to <scene>/text.tsv')
    ap.add_argument('--shots', action='store_true', help='with --text-log: a shot of each new text (t000.png...)')
    ap.add_argument('--root', default=ROOT, help=f'output folder (default {ROOT})')
    ap.add_argument('--shot-after', default='40', help='with --shots: frame delays after a text first draws, e.g. 40,150,400')
    ap.add_argument('--state-at', nargs=2, metavar=('TEXT', 'F'), help='with --text-log: save state F when a drawn text first contains TEXT (e.g. a marker id)')
    ap.add_argument('--all', action='store_true'); ap.add_argument('--jobs', type=int, default=4); ap.add_argument('--match', default='')
    a = ap.parse_args()
    globals()['ROOT'] = a.root
    SHOT_AFTERS[:] = [int(x) for x in a.shot_after.split(',')]
    if a.state_at: STATE_AT[:] = a.state_at
    flags = ['--root', a.root, '--shot-after', a.shot_after] + ['--text-log'] * a.text_log + ['--shots'] * a.shots
    if not a.all:
        try: ok, info = go(a.scene, a.iso, a.state_out, a.text_log and ('shots' if a.shots else 'log'))
        except Exception as e: ok, info = False, f'crash {e!r}'
        print('ok' if ok else 'FAIL', a.scene, info)
        sys.exit(0 if ok else 1)
    todo = [n for n in scenes() if re.search(a.match, n)]   # regex: 'card_ch|game_over'
    os.makedirs(ROOT, exist_ok=True)
    running, results = [], []
    while todo or running:
        while todo and len(running) < a.jobs:
            n = todo.pop(0)
            running.append((n, subprocess.Popen([sys.executable, '-X', 'utf8', __file__, n, '--iso', a.iso] + flags, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)))
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
