"""Replace English lines in batch .out.tsv files from a fixes file of `id|English` lines (a later line wins).

    python -X utf8 tools/tlfix.py work/tl/bNNN.out.tsv FIXES.txt     one batch (every id must be in it)
    python -X utf8 tools/tlfix.py FIXES.txt                          every batch holding one of the ids; prints them

For the fit loop: try candidates with `batches.py fit`, keep the ones that pass in FIXES.txt, apply them here, then
`batches.py merge <the batches printed> --overwrite`.
"""
import glob
import sys


def apply(out, fx, strict=True):
    rows = [l.rstrip('\n').split('\t', 1) for l in open(out, encoding='utf8')]
    have = dict(rows)
    if strict: assert all(i in have for i in fx), f'unknown ids: {sorted(set(fx) - set(have))}'
    hit = [i for i in fx if i in have]
    if hit:
        with open(out, 'w', encoding='utf8', newline='\n') as f:
            for i, en in rows:
                f.write(f"{i}\t{fx.get(i, en)}\n")
    return hit


fixes = sys.argv[-1]
fx = dict(l.rstrip('\n').split('|', 1) for l in open(fixes, encoding='utf8') if '|' in l)
if len(sys.argv) == 3:
    apply(sys.argv[1], fx)
else:
    done = set()
    for out in sorted(glob.glob('work/tl/b*.out.tsv')):
        hit = apply(out, fx, strict=False)
        if hit: print(out.replace('\\', '/').split('/')[-1].split('.')[0], len(hit)); done.update(hit)
    assert done == set(fx), f'ids in no batch: {sorted(set(fx) - done)}'
