"""Replace English lines in a batch's .out.tsv from a fixes file of `id|English` lines (a later line wins).

    python -X utf8 tools/tlfix.py work/tl/bNNN.out.tsv FIXES.txt

For the fit loop: try candidates with `batches.py fit`, keep the ones that pass in FIXES.txt, apply them here.
"""
import sys

out, fixes = sys.argv[1], sys.argv[2]
fx = dict(l.rstrip('\n').split('|', 1) for l in open(fixes, encoding='utf8') if '|' in l)
rows = [l.rstrip('\n').split('\t', 1) for l in open(out, encoding='utf8')]
assert all(i in dict(rows) for i in fx), f'unknown ids: {sorted(set(fx) - set(dict(rows)))}'
with open(out, 'w', encoding='utf8', newline='\n') as f:
    for i, en in rows:
        f.write(f"{i}\t{fx.get(i, en)}\n")
