"""Warp to a stage's talk scene and page through its messages: one shot per message (width gate, marker tours).

    python -X utf8 tools/debug/talk.py stage_1_02_AP --iso build/stress.iso --pages 5 [--wait 240] [--out DIR]

Shots: DIR/p00.png (first message after the settle), p01.png after the first Circle, ...
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gu
from warp import reached, log_text
from scenes import scenes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scene'); ap.add_argument('--iso', default=gu.ORIG); ap.add_argument('--pages', type=int, default=5)
    ap.add_argument('--wait', type=int, default=240); ap.add_argument('--out'); ap.add_argument('--text-log', action='store_true')
    a = ap.parse_args()
    kind, arg, proof = scenes()[a.scene]
    assert kind == 'stage', 'stage scenes only'
    out = a.out or f'work/qa/talk/{a.scene}'
    g = gu.Game(a.iso, out)
    g.watch_files()
    if a.text_log: log_text(g, f'{out}/text.tsv')
    try:
        g.warp(arg); g.new_game()
        ok = g.until(lambda g: reached(g, proof), 24000)
        g.run(480)
        for i in range(a.pages):
            g.shot(f'p{i:02d}.png')
            g.tap('circle', 6, a.wait)
        print('ok' if ok else 'FAIL', a.scene, out)
    finally:
        g.close()


if __name__ == '__main__':
    main()
