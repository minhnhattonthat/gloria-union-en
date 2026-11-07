"""Contact sheets of the unique PTX textures for the graphics-text survey.

    python -X utf8 tools/survey.py OUTDIR [--per-sheet 108] [--sample N]

Every N-th texture of a run of same-size sprites is kept (default 1). Writes sheet_NN.png and index.tsv
(sheet, cell, id, offset, w, h).
"""
import argparse
import hashlib
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(__file__))
import ptx  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--per-sheet", type=int, default=108)
ap.add_argument("--sample", type=int, default=1)
ap.add_argument("--first", type=int, default=0)
ap.add_argument("--last", type=int, default=2964)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
FILES = "work/re/files"
seen = set()
items = []
run = None
count = 0
for i in range(a.first, a.last + 1):
    b = open(f"{FILES}/{i:05d}.bin", "rb").read()
    for t in ptx.scan(b):
        px = b[t["do"]:t["do"] + 256]
        key = hashlib.md5(px + bytes(str((t["w"], t["h"])), "ascii")).digest()
        if key in seen:
            continue
        seen.add(key)
        size = (t["w"], t["h"])
        if size == run:
            count += 1
            if count % a.sample:
                continue
        else:
            run, count = size, 0
        items.append((f"{i}+{t['off']:x}", ptx.decode(b, t), i, t))
with open(f"{a.out}/index.tsv", "w", encoding="utf-8", newline="\n") as idx:
    for s in range(0, len(items), a.per_sheet):
        part = items[s:s + a.per_sheet]
        n = s // a.per_sheet
        ptx.sheet([(x[0], x[1]) for x in part], f"{a.out}/sheet_{n:02d}.png", cell=120, cols=12)
        for k, x in enumerate(part):
            idx.write(f"{n}\t{k}\t{x[2]}\t{x[3]['off']:x}\t{x[3]['w']}\t{x[3]['h']}\n")
print(len(items), "unique textures,", -(-len(items) // a.per_sheet), "sheets")
