"""EBOOT strings: where each cp932 string is and what points at it, from the PRX relocations (work/re/eboot.elf)."""
import re
import struct
from collections import defaultdict, namedtuple

OFF = 0xA0  # file offset = vaddr + OFF
RODATA, DATA, DATA_END = 0x1CA170, 0x2B65F0, 0x3004C8
REL = (0x3008F0, 0x76F40), (0x377A98, 0x34720), (0x3AC1B8, 0xC738)  # .rel.text, .rel.rodata, .rel.data
Str = namedtuple("Str", "addr raw refs")  # refs: ("w", word vaddr) or ("i", lui vaddr, lo vaddr); raw has no NUL


def refs(d):
    """{target vaddr: refs}. Segment 0 only: strings never sit in the cplinit segment. lui/lo pairing by register, in reloc order."""
    out, hi = defaultdict(list), {}
    for base, size in REL:
        for o in range(base, base + size, 8):
            off, info = struct.unpack_from("<II", d, o)
            kind, ofs, val = info & 0xFF, (info >> 8) & 0xFF, (info >> 16) & 0xFF
            if ofs or val:
                continue
            w = struct.unpack_from("<I", d, off + OFF)[0]
            if kind == 2:
                out[w].append(("w", off))
            elif kind == 5:
                hi[(w >> 16) & 31] = (w & 0xFFFF, off)
            elif kind == 6 and (w >> 21) & 31 in hi:
                h, h_off = hi[(w >> 21) & 31]
                out[(h << 16) + struct.unpack("<h", struct.pack("<H", w & 0xFFFF))[0]].append(("i", h_off, off))
    return out


def strend(d, p):
    while d[p]:
        p += 2 if d[p] >= 0x81 and not 0xA0 <= d[p] < 0xE0 else 1
    return p


def text(raw):
    """Decoded string if raw is text the game could draw, else None. Allows the two line breaks; needs one wide character."""
    try:
        u = raw.decode("cp932")
    except UnicodeDecodeError:
        return None
    if not all(ord(c) >= 0x20 or c in "\x01\n" for c in u) or not any(ord(c) >= 0x3000 for c in u):
        return None
    # Binary that happens to decode: half-width kana (the game has none), a lone kanji plus a stray byte, line-break runs.
    if re.search("[｡-ﾟ�]", u) or re.fullmatch(r"[一-鿿][!-~\x01]", u) or "\x01\x01" in u:
        return None
    return u


def pointed(d, rf):
    """Strs at pointer targets in .rodata and .data, by address."""
    out = {}
    for a in sorted(rf):
        if RODATA <= a < DATA_END:
            z = strend(d, a + OFF)
            raw = d[a + OFF:z]
            # code pointing into the middle of a run is a struct base, not a string
            if text(raw) and (d[a + OFF - 1] == 0 or any(r[0] == "w" for r in rf[a])):
                out[a] = Str(a, raw, rf[a])
    return out


RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x01\n])+\x00")


def runs(d, start, end):
    """(vaddr, raw) of NUL-terminated cp932 runs in a range, starting after a NUL or at the run's first good byte."""
    for m in RUN.finditer(d, start + OFF, end + OFF):
        yield m.start() - OFF, m.group()[:-1]
