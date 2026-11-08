"""Translation batches (docs/translator-brief.md): split untranslated text, check translator output, merge it back.

    python -X utf8 tools/batches.py split [--size 3500]   work/tl/bNNN.tsv and build/terms_bNNN.txt for untranslated JP
    python -X utf8 tools/batches.py check [bNNN ...]      a batch's .out.tsv; with no batch, all shipped English (for check.py)
    python -X utf8 tools/batches.py merge bNNN ... [--overwrite]   check, then write the English into script/
    python -X utf8 tools/batches.py fit ID "English"       wrapped lines with px per line against the entry's budget

Copied from the skill's assets/batches.py; the ADAPTER section is this game's. Batches hold each Japanese text once
(19k entries, 13k distinct texts): merge gives the English to every entry with the same JP that has none yet.
Batch TSV: id, speaker, form, limit, JP (line breaks shown as " / "). Output: work/tl/bNNN.out.tsv, id<TAB>English,
every id once, same order. English is one paragraph; the merge wraps it to the window (`\\n` forces a break).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
TL = ROOT / "work/tl"
SCRIPT = ROOT / "script"
GLOSSARY = ROOT / "glossary.md"
MAX_ENTRIES = 150

# ---- ADAPTER: this game's text format ----
FMT = r"%[-+ 0#]*\d*(?:\.\d+)?[hlL]?[diouxXcsfeEgGp%]"
TOKEN = re.compile(r"\[0A\]|" + FMT)  # printf codes must survive; [0A] = a real newline (PSP system dialogs)
FREE = {"[0A]"}  # layout codes the English may place freely
VARIABLE = r"%[-+ 0#]*\d*[di]"  # a number the game draws: "1st" comes out as "1th"
HONORIFICS = {"さん": "-san", "くん": "-kun", "ちゃん": "-chan", "様": "-sama", "サマ": "-sama"}  # D1: kept after names
# split order: names and items first (they seed the glossary), then the story in file order, then the rest
ORDER = ["eboot/names", "eboot/items", "eboot/data", "eboot/ui1", "eboot/ui2", "eboot/ui3", "eboot/messages",
         "eboot/saves", "eboot/system", "story/", "common/", "eboot/barks", "eboot/barks2", "eboot/chants"]
_budget = {}


def docs():
    """(path, doc, entries) per script file, in ORDER."""
    def key(p):
        rel = p.relative_to(SCRIPT).as_posix()
        return next((i for i, o in enumerate(ORDER) if rel.startswith(o)), len(ORDER)), rel
    for path in sorted(SCRIPT.rglob("*.json"), key=key):
        doc = json.loads(path.read_text(encoding="utf-8"))
        yield path, doc, doc


def needs_english(entry):
    return bool(entry.get("jp")) and entry.get("status") != "data" and not entry.get("en")


def group_of(entry):
    return entry["jp"]


def speaker(entry, names={}):
    if not names:
        names.update((j, ens[0]) for jps, ens, _ in glossary() for j in jps)
        names["?"] = ""
    who = entry.get("who") or ""
    return names.get(who, who)


def form(entry):
    k = entry["id"][0]
    return "dlg" if k in "sc" else entry.get("_file", "ui")


def budget(entry):
    """(px, lines, class, measured?, font) or None, from boxes.budget."""
    if entry["id"] not in _budget:
        import boxes
        b = boxes.budget(entry)
        # GROUPS budgets (boxes.GROUPS: 'item name', the EXTRA item page) are font 2; 'sys' is the firmware's
        _budget[entry["id"]] = b and (*b, int(b[2].split("/")[0]) if "/" in b[2] else 2)
    return _budget[entry["id"]]


def byte_limit(entry):
    import insert
    lim = insert.buf_limits().get(entry["id"])
    return entry.get("max") if lim is None else lim


def limit_label(entry):
    b, n = budget(entry), byte_limit(entry)
    out = f"{b[0]}px x{b[1]}{'' if b[3] else '?'}" if b else ""
    if entry["id"] in item_descs():
        out = "item description: wraps by build, %dpx x%d" % min((f[0], f[2]) for f in item_descs()[entry["id"]])
    return (out + f" {n}B").strip() if n else out


def item_descs(_c={}):
    """{entry id: [DESC_FIT tuple]} for item descriptions (the build wraps them, insert.desc_breaks)."""
    if "d" not in _c:
        import insert, eboot as eb
        e = eb.Eboot(insert.ELF.read_bytes()) if insert.ELF.exists() else None
        _c["d"] = {k: [insert.DESC_FIT[t] for t, _ in v] for k, v in insert.item_descs(e).items()} if e else {}
    return _c["d"]


def wrap(en, px, font, cap=999):
    """Greedy word wrap of each forced line to px and cap characters (codes count as written: shortcut, they are
    rare in wrapped windows)."""
    import vwf
    out = []
    for para in en.split("\n"):
        cur = ""
        for w in para.split(" "):
            if cur and (vwf.line_px(cur + " " + w, font) > px or len(cur) + 1 + len(w) > cap):
                out.append(cur)
                cur = w
            else:
                cur = cur + " " + w if cur else w
        out.append(cur)
    return "\n".join(out)


def shipped(entry, en):
    """The English as the build will get it: wrapped to the window when the window has more than one line."""
    b = budget(entry)
    if b and b[1] > 1 and entry["id"] not in item_descs() and "[0A]" not in en:
        import boxes
        return wrap(en, b[0], b[4], boxes.cell_cap(b[2]) if b[2].count("/") == 3 else 999)
    return en


def width_problems(entry, en):
    import vwf, boxes, insert
    out = []
    n = byte_limit(entry)
    if n is not None and "at" not in entry:   # team names (op 0x74, `at`): dead, and the build cuts them to max
        size = insert.fmt_bytes(en) if entry["id"] in insert.buf_limits() else len(insert.from_text(en))
        if size > n:
            out.append(f"{size} bytes, the buffer holds {n}")
    if entry["id"] in item_descs():
        for px, font, lines, nb in item_descs()[entry["id"]]:
            try:
                insert.desc_breaks(en.replace("\n", " "), px, font, lines, nb)
            except ValueError:
                out.append(f"item description over {lines} lines of {px} px")
        return out
    b = budget(entry)
    if not b or b[2] == "sys":
        return out
    px, lines, k, measured, font = b
    rows = TOKEN.sub("", shipped(entry, en)).split("\n")
    cap = boxes.cell_cap(k) if k.count("/") == 3 else 999   # a GROUPS budget ('item name') has no class
    wide = [r for r in rows if vwf.line_px(r, font) > px or len(r) > cap]
    if len(rows) > lines or wide:
        what = f"{len(rows)} lines of max {lines}" if len(rows) > lines else \
            f"{vwf.line_px(wide[0], font)} px / {len(wide[0])} chars over {px} px"
        out.append(("WARN unmeasured window (measure it, don't abbreviate; docs/re/windows.md): " if not measured else "")
                   + what)
    return out


def encodable(char, jp=""):
    """ASCII (the VWF sheets), or a symbol the Japanese already uses (drawn from the Japanese font)."""
    return " " <= char <= "~" or (char in jp and not kind(char) in ("hiragana", "katakana", "kanji")
                                  and not "！" <= char <= "～")
# ---- end of ADAPTER ----


def kind(char):
    if "぀" <= char <= "ゟ":
        return "hiragana"
    if "゠" <= char <= "ヿ":
        return "katakana"
    if "一" <= char <= "鿿" or char == "々":
        return "kanji"
    return "other"


def has_term(jp, term):
    """term occurs as a whole kana or kanji run: ミン isn't in タイミング, くも isn't in ぼくも."""
    for m in re.finditer(re.escape(term), jp):
        a, b = m.start(), m.end()
        if (a == 0 or kind(jp[a - 1]) != kind(term[0])) and (b == len(jp) or kind(jp[b]) != kind(term[-1])):
            return True
    return False


def glossary(_c={}):
    """[(JP forms, EN forms, avoid forms)] from glossary.md's | JP | EN | max | notes | Avoid | tables."""
    if GLOSSARY in _c:
        return _c[GLOSSARY]
    rows = []
    if GLOSSARY.exists():
        for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if line.startswith("|") and len(cells) >= 2 and cells[0] not in ("JP", "") and not set(cells[0]) <= set("-: "):
                avoid = [x.strip() for x in cells[4].split("/") if x.strip()] if len(cells) > 4 else []
                rows.append(([x.strip() for x in cells[0].split("/")], [x.strip() for x in cells[1].split("/")], avoid))
    _c[GLOSSARY] = rows
    return rows


def problems(entry, en, terms):
    """Every rule, on one line of English. Lines starting WARN don't fail the check."""
    jp = entry["jp"]
    if not en.strip():
        return ["empty English"]
    out = []
    plain = TOKEN.sub("", en)
    if bad := sorted({c for c in plain if not encodable(c, jp) and c != "\n"}):
        out.append(f"unencodable characters {bad}")
    if re.search(r"\\u[0-9a-fA-F]{4}", en) or "\t" in en or "\\n" in en:
        out.append("escape sequence or tab in the English")
    want = Counter(t for t in TOKEN.findall(jp) if t not in FREE)
    have = Counter(t for t in TOKEN.findall(en) if t not in FREE)
    if want != have:
        out.append(f"control codes differ: JP {dict(want)} EN {dict(have)}")
    if re.search(VARIABLE + r"(st|nd|rd|th)\b", en):
        out.append('ordinal suffix after a variable (write "No. %d")')
    jp_plain = TOKEN.sub("", jp)
    en = en.replace("\n", " ")   # merged English is wrapped: a term may span a line break
    for jps, ens, avoid in terms:
        for hon, hon_en in HONORIFICS.items():
            if any(j + hon in jp_plain for j in jps) and not any(e.lower() + hon_en in en.lower() for e in ens):
                out.append(f"honorific {jps[0]}{hon} needs {ens[0]}{hon_en}")
        if not any(has_term(jp_plain, j) for j in jps):
            continue   # Avoid spellings too: "Gang" is a misspelt Gangr only where ガング is in the line
        if not any(e.lower() in en.lower() for e in ens):
            out.append(f"glossary: {jps[0]} -> {ens[0]}")
        out += [f"glossary Avoid: {a}" for a in avoid if re.search(rf"\b{re.escape(a)}\b", en)]
    return out + width_problems(entry, en)


def failing(ps):
    return [p for p in ps if not p.startswith("WARN")]


def index():
    out = {}
    for path, _, entries in docs():
        for e in entries:
            e["_file"] = path.stem if path.parent.name == "eboot" else path.parent.name
            out[e["id"]] = e
    return out


def read_tsv(path):
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_out(path):
    """Output rows; a literal \\n in the English is a forced line break."""
    return [(r[0], "\t".join(r[1:]).replace("\\n", "\n")) for r in read_tsv(path)]


def existing():
    return sorted(TL.glob("b[0-9][0-9][0-9].tsv"))


def split(size):
    """Numbers on from the last batch and leaves out texts already batched, so a repeat run can't duplicate work."""
    TL.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    entries = index()
    taken = {entries[r[0]]["jp"] for p in existing() for r in read_tsv(p) if r[0] in entries}
    n = max((int(p.stem[1:]) for p in existing()), default=0)
    groups = {}
    for e in entries.values():
        if needs_english(e) and e["jp"] not in taken:
            groups.setdefault(group_of(e), []).append(e)
    batches, cur, chars = [], [], 0
    for group in groups.values():
        c = len(TOKEN.sub("", group[0]["jp"]))
        if cur and (chars + c > size or len(cur) >= MAX_ENTRIES or cur[-1]["_file"] != group[0]["_file"] and
                    form(cur[-1]) != form(group[0])):
            batches.append(cur)
            cur, chars = [], 0
        cur.append(group[0])
        chars += c
    if cur:
        batches.append(cur)
    terms = glossary()
    for batch in batches:
        n += 1
        name = f"b{n:03d}"
        path = TL / f"{name}.tsv"
        if path.exists():
            sys.exit(f"{path} already exists")
        rows = [f"{e['id']}\t{speaker(e)}\t{form(e)}\t{limit_label(e)}\t{e['jp'].replace(chr(10), ' / ')}" for e in batch]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
        jps = " ".join(TOKEN.sub("", e["jp"]) for e in batch)
        used = [(j, ens[0]) for jpl, ens, _ in terms for j in jpl if has_term(jps, j)]
        (ROOT / f"build/terms_{name}.txt").write_text("".join(f"{j}\t{e}\n" for j, e in used)
                                                      or "(no glossary terms in this batch)\n", encoding="utf-8", newline="\n")
    print(f"{len(batches)} new batches in {TL}, {len(taken)} texts already batched")


def same_jp(entries):
    out = {}
    for e in entries.values():
        out.setdefault(e["jp"], []).append(e)
    return out


def check_batch(batch, entries, terms, groups):
    want = [r[0] for r in read_tsv(TL / f"{batch}.tsv")]
    rows = read_out(TL / f"{batch}.out.tsv")
    bad = []
    if [r[0] for r in rows] != want:
        got = [r[0] for r in rows]
        dup = sorted(i for i, c in Counter(got).items() if c > 1)
        bad.append(f"ids differ: missing {sorted(set(want) - set(got))[:8]} extra {sorted(set(got) - set(want))[:8]} "
                   f"duplicate {dup[:8]} (order must match too)")
    warns = []
    for eid, en in rows:
        if eid not in entries:
            continue
        for m in groups[entries[eid]["jp"]]:   # every entry that will get this English
            if m["en"] and m["id"] != eid:
                continue
            for p in problems(m, en, terms):
                line = f"{eid}{'' if m['id'] == eid else ' (as ' + m['id'] + ')'}: {p}: {en!r}"
                (warns if p.startswith("WARN") else bad).append(line)
    return bad, warns, dict(rows)


def merge(new, overwrite, entries, groups):
    """Refuses to replace different English unless told to, before anything is written."""
    target = {}
    for eid, en in new.items():
        for m in groups[entries[eid]["jp"]]:
            if overwrite or m["id"] == eid or not m.get("en"):  # overwrite: the copies of the same JP too
                target[m["id"]] = shipped(m, en)
    if not overwrite:
        for eid, en in target.items():
            if entries[eid].get("en") and entries[eid]["en"] != en:
                sys.exit(f"{eid} would lose {entries[eid]['en']!r}: pass --overwrite if that is meant")
    changed = 0
    for path, doc, _ in docs():
        touched = False
        for e in doc:
            if e["id"] in target and e.get("en") != target[e["id"]]:
                e["en"], e["status"] = target[e["id"]], "done"
                touched = True
                changed += 1
        if touched:
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"merged: {changed} entries changed")


def fit(eid, en):
    import vwf
    e = index()[eid]
    b = budget(e)
    print(f"{eid}: budget {b}")
    for row in shipped(e, en).split("\n"):
        print(f"{vwf.line_px(TOKEN.sub('', row), b[4] if b else 1):4d} px  {row}")
    print("\n".join(problems(e, en, glossary())) or "OK")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "split":
        return split(int(args[args.index("--size") + 1]) if "--size" in args else 3500)
    if cmd == "fit":
        return fit(*args)
    overwrite = "--overwrite" in args
    names = [a for a in args if a != "--overwrite"]
    entries, terms = index(), glossary()
    if cmd == "check" and not names:
        ps = [(i, p, e["en"]) for i, e in entries.items() if e.get("en") and e.get("status") != "data"
              for p in problems(e, e["en"], terms)]
        bad = [f"{i}: {p}: {en!r}" for i, p, en in ps if not p.startswith("WARN")]
        print(f"{len(entries)} entries, {sum(1 for e in entries.values() if e.get('en'))} in English, "
              f"{len(bad)} problems, {len(ps) - len(bad)} warnings")
        print("\n".join(bad[:200]))
        return 1 if bad else 0
    if cmd not in ("check", "merge") or not names:
        sys.exit(__doc__)
    groups = same_jp(entries)
    new, failed = {}, 0
    for batch in names:
        bad, warns, rows = check_batch(batch, entries, terms, groups)
        new.update(rows)
        failed += bool(bad)
        print(f"{batch}: " + ("OK" if not bad else f"{len(bad)} problems") + (f", {len(warns)} warnings" if warns else ""))
        for line in bad + warns:
            print("  " + line)
    if failed:
        return 1
    if cmd == "merge":
        merge(new, overwrite, entries, groups)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
