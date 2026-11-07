"""Extract text to script/*.json (phase 4). Sources: work/re/files, work/re/eboot.elf (AGENTS.md, Unpack).

    python -X utf8 tools/extract.py           refuses to touch script/ if it exists: English lives there
    python -X utf8 tools/extract.py --force   only with no English yet

Files: script/story/<cpk id>.json, script/common/sub<n>.json (id 3 section 15), script/eboot/<group>.json.
Entry: id, jp, en, status (todo, or data = not shown to players), then where it lives:
- slots: the u32 fields that hold its offset (story, common), or "w:<vaddr>" / "i:<lui vaddr>:<lo vaddr>" (EBOOT)
- at, max: bytes in place, for text that has no pointer (op 0x74 team names, sub 5 and 6)
- voice: the id in its `02 00` tag; who: speaker's Japanese name, or #<id> when not named (context only, a guess past id 0x0E)
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import elf  # noqa: E402
import vm  # noqa: E402

FILES = ROOT / "work/re/files"
ELF = ROOT / "work/re/eboot.elf"
OUT = ROOT / "script"
STORY = range(2032, 2083)
SUBS = 3, 15  # CPK id, section
SUB_TEXT = 0, 1, 2, 3, 5, 6, 7, 8, 9  # sub 4 is code with no text
BARE = 5, 6  # NUL-separated strings, no code; how they are reached is not known
# speaker ids of `eb` follow the unit name pool at 0x2808F0 with its team forms dropped (guess past 0x0E, lines read right);
# 0x0F has 87 lines and no name in that pool
WHO = ("イシュト ピンガー ルルゥ ザザーランド エリーシャ ミネソタ ロコモコ ラズベリー ガング フィービー アンヌ カミュル ユグドラ パメラ イータ "
       "#15 ベルガス ブラックモア ローガン トレイシー ガルム メラニー ガリオレッド アシュレイ アジョー ジゼル サイード キーラ エンリエッタ").split()
# (first vaddr, past last, why) strings in the EBOOT that players never see
NOT_TEXT = (
    (0x1CA384, 0x1CA3F0, "debug"), (0x1CA468, 0x1CA46A, "binary"), (0x1DCB28, 0x1DCB2A, "binary"),
    (0x1ED94C, 0x1ED94D, "binary"), (0x24F0E8, 0x24F350, "binary"), (0x2B7698, 0x2B769A, "binary"),
    (0x2C7510, 0x2C7512, "binary"), (0x2C858C, 0x2C858E, "binary"), (0x2F9180, 0x2F9182, "binary"), (0x2F9E00, 0x2FA2E0, "binary"),
    (0x2537C0, 0x253874, "glyph list"), (0x253CD8, 0x253D10, "binary"), (0x25D030, 0x25DDF0, "debug"),
    (0x27FFC8, 0x2804A8, "debug"), (0x2823A8, 0x2823C0, "debug"), (0x2896E0, 0x2896F0, "binary"),
    (0x2AB000, 0x2B6630, "binary"), (0x2FA2E0, 0x2FA300, "library banner"),
)
# EBOOT file groups by vaddr: what the block holds (read from the strings)
GROUPS = (
    (0x1CA000, "system"), (0x1ED000, "messages"), (0x1EE000, "barks"), (0x215000, "chants"), (0x230000, "barks2"),
    (0x24F000, "ui1"), (0x254000, "ui2"), (0x25C000, "items"), (0x25D000, "saves"), (0x280000, "names"), (0x283000, "ui3"),
    (0x2B6000, "data"),
)


def fct(b, n):
    """Section n of an FCT, as bytes."""
    assert b[:4] == b"FCT\0"
    h = struct.unpack_from("<I", b, 8)[0]
    off, size = struct.unpack_from("<II", b, h + 8 * n)
    return b[off:off + size]


def to_text(raw):
    """cp932 bytes -> JSON text. 01 -> newline; a real \\n only occurs in EBOOT strings, as [0A]."""
    return raw.decode("cp932").replace("\n", "[0A]").replace("\x01", "\n")


def from_text(s):
    return s.replace("\n", "\x01").replace("[0A]", "\n").encode("cp932")


def tagged(b, s):
    """Text span -> (voice id or None, body bytes). A span holds at most one tag (checked here)."""
    tag, body = vm.split_text(b[s.off:s.end])
    assert len(tag) in (0, 4), hex(s.off)
    return struct.unpack_from("<H", tag, 2)[0] if tag else None, body


def script_entries(b, spans, prefix, who=True):
    """Entries of one script, in file order, with their slots and last speaker."""
    slots, inline, speaker, by_text = {}, [], None, {}
    for s in spans:
        if s.kind != "op":
            continue
        if s.op == 0xEB:
            speaker = struct.unpack_from("<H", b, s.off + 4)[0]
        elif s.op == 0x46 and b[s.off + 1] == 7:
            t = struct.unpack_from("<I", b, s.off + 3)[0]
            slots.setdefault(t, []).append(s.off + 3)
            by_text.setdefault(t, speaker)
        elif s.op == 0x74:
            inline.append(s)
    out = []
    for s in spans:
        if s.kind == "text":
            voice, body = tagged(b, s)
            e = {"id": f"{prefix}:{s.off:05x}", "jp": to_text(body), "en": "", "status": "todo",
                 "slots": [f"0x{x:x}" for x in slots.get(s.off, [])]}
            if voice is not None:
                e["voice"] = voice
            sp = by_text.get(s.off)
            if sp is not None:
                e["who"] = WHO[sp] if sp < len(WHO) else f"#{sp}"
            out.append(e)
    for s in inline:
        raw = b[s.off + 3:s.end - 1]
        out.append({"id": f"{prefix}:{s.off:05x}t", "jp": to_text(raw), "en": "", "status": "todo", "at": f"0x{s.off + 3:x}",
                    "max": len(raw), "who": "team name"})
    return out


def sub_spans(b, n):
    """Spans of common sub n. Sub 7 has the story layout; the others open with a u32 table, then code."""
    if n == 7:
        return vm.parse(b, 0x10, struct.unpack_from("<I", b, 0)[0])
    return vm.parse(b, struct.unpack_from("<I", b, 0)[0], len(b))


def bare_entries(b, prefix):
    out, p = [], 0
    while p < len(b):
        z = b.index(0, p)
        out.append({"id": f"{prefix}:{p:05x}", "jp": to_text(b[p:z]), "en": "", "status": "todo", "at": f"0x{p:x}", "max": z - p})
        p = z + 1
    return out


def eboot_entries(d):
    """{group: entries}, by address."""
    groups = {}
    names = [g[1] for g in GROUPS]
    starts = [g[0] for g in GROUPS]
    for a, s in elf.pointed(d, elf.refs(d)).items():
        g = names[max(i for i, x in enumerate(starts) if x <= a)]
        why = next((w for lo, hi, w in NOT_TEXT if lo <= a < hi), None)
        e = {"id": f"e:{a:06x}", "jp": to_text(s.raw), "en": "", "status": "data" if why else "todo",
             "slots": [":".join([r[0]] + [f"{x:x}" for x in r[1:]]) for r in s.refs]}
        if why:
            e["notes"] = why
        groups.setdefault(g, []).append(e)
    return groups


def all_files():
    """{path under script/: entries}"""
    out = {}
    for i in STORY:
        b = (FILES / f"{i:05d}.bin").read_bytes()
        out[f"story/{i}.json"] = script_entries(b, vm.parse(b), f"s{i}")
    sec = fct((FILES / f"{SUBS[0]:05d}.bin").read_bytes(), SUBS[1])
    for n in SUB_TEXT:
        b = fct(sec, n)
        out[f"common/sub{n}.json"] = bare_entries(b, f"c{n}") if n in BARE else script_entries(b, sub_spans(b, n), f"c{n}")
    for g, entries in eboot_entries(ELF.read_bytes()).items():
        out[f"eboot/{g}.json"] = entries
    return out


if __name__ == "__main__":
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit("script/ exists: extract would overwrite English. Use --force only if none is there.")
    if OUT.exists() and any(e["en"] for f in OUT.glob("*/*.json") for e in json.loads(f.read_text("utf8"))):
        sys.exit("script/ holds English: refusing, even with --force.")
    n = 0
    for name, entries in all_files().items():
        p = OUT / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", "utf8", newline="\n")
        n += len(entries)
    print(n, "entries")
