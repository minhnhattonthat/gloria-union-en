"""Story script reader (CPK ids 2032-2082): the whole file as a list of spans.

File: u32 end_of_code, entry points (code offsets; the count varies), then text and code interleaved up to end_of_code,
then a 0x14-byte trailer. Instruction: <op> <total length> <args>. Exceptions, from the handlers (table at 0x2EF748):
- 0x74 `74 05 <side> <NUL-terminated name>`: the handler ignores the length byte and uses strlen.
- 0x52, 0x53 `op 02` + 5 or 3 u32 targets, indexed by a save byte.
- 0x06 is `return`, so anything may follow it, including a 4-aligned u32 target table.
Text: cp932, NUL-terminated. 01 = line break; `02 00 <u16 id>` = 4-byte tag (voice line), usually first, skipped by the
line counter at 0x119BD0. 0x90 pads to a 4-aligned address.
"""
import re
import struct
from collections import namedtuple

Span = namedtuple("Span", "off end kind op")  # kind: head op table pad text trailer; op: opcode, for kind op
SHOW = b"\x46\x07\x00"  # 46 07 00 <u32 offset of the text>: show a message


def header(b):
    """-> (end_of_code, [entries], first offset past the entries)"""
    end = struct.unpack_from("<I", b, 0)[0]
    entries, p = [], 4
    while True:
        v = struct.unpack_from("<I", b, p)[0]
        if v >= end or v < 8:
            break
        entries.append(v)
        p += 4
    return end, entries, p


def strend(b, p):
    """Offset of the NUL ending the cp932 string at p. Stepping by characters: a trail byte can be anything."""
    while b[p]:
        p += 2 if b[p] >= 0x81 and not 0xA0 <= b[p] < 0xE0 else 1
    return p


def targets(b, end):
    """Text offsets named by SHOW, from a byte sweep (the walk needs them, so this comes first; parse() checks it)."""
    found = {struct.unpack_from("<I", b, m.start() + 3)[0] for m in re.finditer(re.escape(SHOW), b[:end])}
    return {v for v in found if v < end}


def parse(b, p=None, end=None):
    """Every byte of the file, in order, as Spans. Asserts on anything it can't name."""
    if p is None:
        end, _, p = header(b)
    tg = targets(b, end)
    out = [Span(0, p, "head", None)]

    def add(q, kind, op=None):
        nonlocal p
        out.append(Span(p, q, kind, op))
        p = q

    while p < end:
        q = p
        while b[q] == 0x90:
            q += 1
        if q > p and p not in tg and q % 4 == 0:
            add(q, "pad")
            continue
        op, n = b[p], b[p + 1]
        if p in tg or b[p:p + 2] == b"\x02\x00" or n > 40:  # no instruction is longer than 40 bytes; a cp932 trail byte is
            q = p
            while b[q:q + 2] == b"\x02\x00" and q + 4 not in tg:
                q += 4
            if b[q:q + 2] == b"\x02\x00":  # one script has a tag with no text in front of a message
                add(q + 4, "pad")
            else:
                add(strend(b, q) + 1, "text")
            continue
        assert n >= 2, (hex(p), b[p:p + 8].hex())
        if op == 0x74:
            add(strend(b, p + 3) + 1, "op", op)
            continue
        add(p + n + {0x52: 20, 0x53: 12}.get(op, 0), "op", op)
        if op == 6:
            q = p
            while q < end and b[q] in (0, 0x90):
                q += 1
            if q > p and q % 4 == 0:
                add(q, "pad")
            if p % 4 == 0 and p + 8 <= end and max(struct.unpack_from("<II", b, p)) < end:  # one u32 alone can be `e8 07 00 00`
                while p < end and struct.unpack_from("<I", b, p)[0] < end:
                    add(p + 4, "table")
    assert p == end, (hex(p), hex(end))
    add(len(b), "trailer")
    return out


def split_text(raw):
    """Text span bytes -> (tag bytes, cp932 body without its NUL)."""
    q = 0
    while raw[q:q + 2] == b"\x02\x00":
        q += 4
    return raw[:q], raw[q:-1]
