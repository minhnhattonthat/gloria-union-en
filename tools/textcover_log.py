"""Text-coverage logs for PPSSPP (no Lua): turn warp.py --text-log output into what $SKILL/scripts/textcover.py reads.

    python -X utf8 tools/textcover_log.py TOUR_DIR [TOUR_DIR..] --strings work/qa/cover/strings.tsv --out work/qa/cover

Writes STRINGS (one "id<TAB>hex index" per script string with English) and OUT/<tour>/<scene>/log.txt with a
"TEXT <hex index>" line for each string a scene's text.tsv drew. The hook logs the drawn text, not the address it
was read from (script files load at varying RAM addresses), so a string counts as shown when a drawn text equals
it (format specifiers match anything) or, for drawn texts of 12+ characters, is part of it (one page of a message).
Then: python -X utf8 $SKILL/scripts/textcover.py work/qa/cover work/qa/cover/strings.tsv --waive docs/text_unshown.tsv
"""
import argparse, bisect, csv, glob, json, os, re, sys

FMT = re.compile(r'%[-0-9.]*[sdx]')


def norm(t):
    return ' '.join(t.replace('\\n', ' ').replace('[0A]', ' ').replace('\n', ' ').split())


def load_strings():
    out = []
    for f in sorted(glob.glob('script/**/*.json', recursive=True)):
        for s in json.load(open(f, encoding='utf8')):
            if s.get('en') and s.get('status') != 'data': out.append((s['id'], norm(s['en'])))
    return out


def matcher(strings):
    exact, pats, starts, parts = {}, [], [], []
    pos = 0
    for i, (_, t) in enumerate(strings):
        exact.setdefault(t, []).append(i)
        if FMT.search(t): pats.append((re.compile('^' + FMT.sub('\0', re.escape(t)).replace('\0', '.*?') + '$'), i))
        starts.append(pos); parts.append(t); pos += len(t) + 1
    blob = '\x02'.join(parts)

    def find(drawn):
        d = norm(drawn)
        hits = set(exact.get(d, ()))
        hits.update(i for p, i in pats if p.match(d))
        if len(d) >= 12:
            k = blob.find(d)
            while k >= 0:
                hits.add(bisect.bisect_right(starts, k) - 1); k = blob.find(d, k + 1)
        return hits
    return find


def selftest():
    s = [('a', 'Hello there,\nfriend.'), ('b', '%2d fought %2dW'), ('c', 'OK'), ('d', 'A long message.\nSecond page here.')]
    f = matcher([(i, norm(t)) for i, t in s])
    assert f('Hello there,\\nfriend.') == {0} and f('12 fought  3W') == {1} and f('OK') == {2}
    assert f('Second page here.') == {3} and f('page') == set()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tours', nargs='+'); ap.add_argument('--strings', default='work/qa/cover/strings.tsv')
    ap.add_argument('--out', default='work/qa/cover')
    a = ap.parse_args()
    selftest()
    strings = load_strings()
    os.makedirs(os.path.dirname(a.strings), exist_ok=True)
    with open(a.strings, 'w', encoding='utf8') as f:
        for i, (sid, _) in enumerate(strings): f.write(f'{sid}\t{i + 1:x}\n')
    find = matcher(strings)
    total = set()
    for tour in a.tours:
        for tsv in glob.glob(os.path.join(tour, '*', 'text.tsv')):
            scene = os.path.basename(os.path.dirname(tsv))
            hits = set()
            with open(tsv, encoding='utf8') as f:
                for row in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE): hits |= find(row['text'] or '')
            d = os.path.join(a.out, os.path.basename(os.path.normpath(tour)), scene)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'log.txt'), 'w') as f: f.writelines(f'TEXT {i + 1:x}\n' for i in sorted(hits))
            total |= hits
    print(f'{len(total)}/{len(strings)} strings drawn', file=sys.stderr)


if __name__ == '__main__':
    main()
