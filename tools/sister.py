"""English the sister game's fan patch (Blaze Union repo next to this one) gave the same Japanese text.

    python -X utf8 tools/sister.py bNNN [--repo DIR]   print id, JP, Blaze Union English for every exact JP match

Reference only: the glossary wins. Yggdra Union (USA) card names reached that repo through its D14/D15.
"""
import argparse
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(os.path.dirname(ROOT), "blaze-union-story-to-reach-the-future-en")


def table(repo):
    out = {}
    for f in glob.glob(os.path.join(repo, "script", "*.json")):
        for e in json.load(open(f, encoding="utf8")):
            if isinstance(e, dict) and e.get("jp") and e.get("en"):
                out.setdefault(e["jp"].strip(), e["en"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch")
    ap.add_argument("--repo", default=REPO)
    a = ap.parse_args()
    t = table(a.repo)
    for line in open(os.path.join(ROOT, "work", "tl", a.batch + ".tsv"), encoding="utf8"):
        c = line.rstrip("\n").split("\t")
        jp = c[4].replace(" / ", "{n}").strip()  # Blaze Union writes line breaks as {n}
        en = t.get(jp) or t.get(c[4].strip())
        if en:
            print(f"{c[0]}\t{c[4]}\t{en!r}")


if __name__ == "__main__":
    main()
