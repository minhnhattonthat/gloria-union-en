"""Story script reader (CPK ids 2032-2082): messages and the instruction walk.

File: u32 end_of_code, then entry points (code offsets; the count varies), the text block, code up to end_of_code,
then a trailer. Text block: NUL-terminated cp932 strings, some prefixed 02 00 <u16 id> (voice-line records).
Instruction: <op> <total length> <args>, except op 0x74 (+ inline NUL-terminated string after its args).
"""
import struct

INLINE_STR = {0x74}


def header(b):
    """-> (end_of_code, [entries], text_start)"""
    end = struct.unpack_from("<I", b, 0)[0]
    entries, p = [], 4
    while True:
        v = struct.unpack_from("<I", b, p)[0]
        if v >= end or v < 8:
            break
        entries.append(v)
        p += 4
    return end, entries, p


def _clean(s):
    try:
        t = s.decode("cp932")
    except UnicodeDecodeError:
        return False
    return len(t) > 0 and all(ord(c) >= 0x20 or c == "\x01" for c in t)


def _strend(b, p):
    while b[p]:
        p += 2 if b[p] >= 0x81 and not 0xA0 <= b[p] < 0xE0 else 1
    return p


def messages(b):
    """-> ([(offset of record, id or None, raw text bytes)], code_start). `offset` is what code refers to."""
    end, entries, p = header(b)
    out = []
    while p < end:
        rec, mid, q = p, None, p
        if b[p:p + 2] == b"\x02\x00":
            mid = struct.unpack_from("<H", b, p + 2)[0]
            q += 4
        z = _strend(b, q)
        if not _clean(b[q:z]):
            return out, rec
        out.append((rec, mid, b[q:z]))
        p = z + 1
    raise AssertionError("no code")


def walk(b):
    """Yield (offset, op, args bytes, inline string or None) over the code area."""
    end, entries, _ = header(b)
    _, p = messages(b)
    while p < end:
        op, n = b[p], b[p + 1]
        assert n >= 2, (hex(p), hex(op), n)
        if op in INLINE_STR:
            z = _strend(b, p + n)
            yield p, op, b[p + 2:p + n], b[p + n:z]
            p = z + 1
        else:
            yield p, op, b[p + 2:p + n], None
            p += n
    assert p == end, (hex(p), hex(end))
