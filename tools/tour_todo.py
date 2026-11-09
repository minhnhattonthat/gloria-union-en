"""Scenes a tour log has no `ok` line for, plus any named extra scenes, as one `warp.py --all --match` regex.

    python -X utf8 tools/tour_todo.py work/qa/final.log [EXTRA ...]   -> prints ^(a|b|...)$ ; count on stderr
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'debug'))
from scenes import scenes  # noqa: E402

log, *extra = sys.argv[1:]
ok = {ln.split()[1] for ln in Path(log).read_text('utf8').splitlines() if ln.startswith('ok ')}
todo = [n for n in scenes() if n not in ok or n in extra]
assert set(extra) <= set(scenes()), f"unknown scenes: {set(extra) - set(scenes())}"
print(f'{len(todo)} scenes', file=sys.stderr)
print('^(' + '|'.join(map(re.escape, todo)) + ')$')
