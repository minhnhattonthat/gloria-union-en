"""Story-pass chapter files: every story line in story order as `>> id | speaker | JP` / `   EN`.

    python -X utf8 tools/pairs.py --chapters [OUT=work/qa/story/chapters]

Chapters follow docs/synopsis.md (story file ranges in CHAPTERS); a chapter longer than PART entries is cut into
parts (ch4-1, ch4-2...) so one review reads one part. Whitespace-only lines (blank letter boxes) are left out.
Then: qa_gate.py init work/qa/story/manifest.tsv work/qa/story/chapters --glob "*.txt" (references/translation.md §Review).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = {1: (2032, 2037), 2: (2038, 2042), 3: (2043, 2046), 4: (2047, 2059), 5: (2060, 2067), 6: (2068, 2077),
            7: (2078, 2082)}
PART = 260


def lines(lo, hi, sub='story'):
    names = [str(n) for n in range(lo, hi + 1)] if sub == 'story' else \
        sorted(p.stem for p in (ROOT / f'script/{sub}').glob('*.json'))
    for n in names:
        p = ROOT / f'script/{sub}/{n}.json'
        for e in json.loads(p.read_text('utf8')) if p.exists() else []:
            if e.get('jp', '').strip() and e.get('status') != 'data':
                yield (f">> {e['id']} | {e.get('who', '')} | {e['jp'].replace(chr(10), ' / ')}\n"
                       f"   {e.get('en', '').replace(chr(10), ' ')}\n")


def chapters(out):
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('*.txt'):
        old.unlink()
    for ch, (lo, hi) in [*CHAPTERS.items(), ('cm', (0, 0))]:   # cm: common text (tutorials, reactions, battle talk)
        rows = list(lines(lo, hi, 'common' if ch == 'cm' else 'story'))
        parts = [rows[i:i + PART] for i in range(0, len(rows), PART)] or [[]]
        for i, part in enumerate(parts, 1):
            stem = 'cm' if ch == 'cm' else f'ch{ch}'
            name = stem if len(parts) == 1 else f'{stem}-{i}'
            title = 'Common text (script/common)' if ch == 'cm' else f'Chapter {ch} ({lo}-{hi})'
            (out / f'{name}.txt').write_text(f'# {title}, part {i} of {len(parts)}\n' + ''.join(part),
                                             encoding='utf-8', newline='\n')
            print(name, len(part))
    seen = set()   # EBOOT tables: each distinct JP once (batches translated it once), per table file
    for p in sorted((ROOT / 'script/eboot').glob('*.json')):
        rows = []
        for e in json.loads(p.read_text('utf8')):
            if e.get('jp', '').strip() and e.get('status') != 'data' and e.get('en') and e['jp'] not in seen:
                seen.add(e['jp'])
                rows.append(f">> {e['id']} | {e['jp'].replace(chr(10), ' / ')}\n   {e['en'].replace(chr(10), ' / ')}\n")
        for i in range(0, len(rows), PART * 2):   # short rows: twice as many per part
            name = f'eb-{p.stem}-{i // (PART * 2) + 1}'
            (out / f'{name}.txt').write_text(f'# EBOOT table {p.stem}\n' + ''.join(rows[i:i + PART * 2]),
                                             encoding='utf-8', newline='\n')
            print(name, len(rows[i:i + PART * 2]))


if __name__ == '__main__':
    if sys.argv[1:2] != ['--chapters']:
        sys.exit(__doc__)
    chapters(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'work/qa/story/chapters')
