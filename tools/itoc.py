"""CPK with an ITOC only (files by id, no names): list and read.

    python -X utf8 tools/itoc.py list work/re/data.bin
    python -X utf8 tools/itoc.py x work/re/data.bin OUTDIR     # one file per id, CRILAYLA expanded

Entries in id order, each at the next Align boundary from ContentOffset (checked by test_itoc).
"""
import struct
import sys
from collections import namedtuple
from pathlib import Path

import cpk

Item = namedtuple("Item", "id off csize size")


def read_toc(b):
    """b: the CPK's first bytes, through the end of the ITOC."""
    r = cpk.Utf(b, 0x10).rows[0]
    base = r["ItocOffset"]
    assert b[base:base + 4] == b"ITOC"
    u = cpk.Utf(b, base + 0x10).rows[0]
    rows = []
    for key in ("DataL", "DataH"):
        _, off, n = u[key]
        if n:
            rows += cpk.Utf(b, off).rows
    rows.sort(key=lambda x: x["ID"])
    pos, align, out = r["ContentOffset"], r["Align"], []
    for x in rows:
        out.append(Item(x["ID"], pos, x["FileSize"], x["ExtractSize"]))
        pos += -(-x["FileSize"] // align) * align
    return r, out


def sub_table(old, rows):
    """DataL/DataH table `old` with new rows (bytes): strings kept, size fields updated, padded to 8 like the originals."""
    size, rows_off, str_off, data_off, name_off, ncols, rowlen, nrows = struct.unpack_from(">IIIIIHHI", old, 4)
    strs = old[8 + str_off:].rstrip(b"\0") + b"\0"
    out = bytearray(old[:8 + rows_off] + rows + strs)
    out += bytes(-len(out) % 8)
    struct.pack_into(">IIII", out, 4, len(out) - 8, rows_off, rows_off + len(rows), len(out) - 8)
    struct.pack_into(">I", out, 28, len(rows) // rowlen)
    return bytes(out)


def pack(b, repl):
    """The CPK b (whole file) with ids in repl replaced, stored plain (FileSize == ExtractSize).
    Ids keep their order and Align; anything over 64K goes in DataH, as in the original."""
    r, items = read_toc(b[:r_end(b)])
    align = r["Align"]
    parts = [(i, repl.get(i.id)) for i in items]
    rows = [(i.id, *((len(d), len(d)) if d is not None else (i.csize, i.size))) for i, d in parts]

    base = r["ItocOffset"]
    u = cpk.Utf(b, base + 0x10)
    row = u.rows[0]
    old_l, old_h = (b[row[k][1]:row[k][1] + row[k][2]] for k in ("DataL", "DataH"))
    low = [x for x in rows if max(x[1:]) < 0x10000]
    high = [x for x in rows if max(x[1:]) >= 0x10000]
    data_l = sub_table(old_l, b"".join(struct.pack(">HHH", *x) for x in low))
    data_h = sub_table(old_h, b"".join(struct.pack(">HII", *x) for x in high))

    data_off = struct.unpack_from(">I", b, base + 0x10 + 16)[0]
    size = data_off + len(data_l) + len(data_h)
    outer = bytearray(b[base + 0x10:base + 0x10 + 8 + data_off])
    struct.pack_into(">I", outer, 4, size)
    struct.pack_into(">IIIIII", outer, 8 + u.rows_off, len(low), len(high), 0, len(data_l), len(data_l), len(data_h))
    itoc = b[base:base + 8] + struct.pack("<I", size + 8) + b[base + 12:base + 16] + bytes(outer) + data_l + data_h
    assert base + len(itoc) <= r["ContentOffset"], "ITOC outgrew its gap: move ContentOffset"

    sizes = [x[1] for x in rows]
    head = bytearray(r["ContentOffset"])
    head[:base] = b[:base]
    head[base:base + len(itoc)] = itoc
    info = cpk.Utf(b, 0x10)
    ends = sum(-(-n // align) * align for n in sizes)
    info.set(head, 0, "ItocSize", len(itoc))
    info.set(head, 0, "ContentSize", ends)
    info.set(head, 0, "EnabledDataSize", sum(sizes))
    info.set(head, 0, "EnabledPackedSize", sum(x[2] for x in rows))

    out = bytearray(r["ContentOffset"] + ends - (-sizes[-1] % align))
    out[:len(head)] = head
    view, src, pos = memoryview(out), memoryview(b), r["ContentOffset"]
    for i, d in parts:
        n = i.csize if d is None else len(d)
        view[pos:pos + n] = src[i.off:i.off + n] if d is None else d
        pos += -(-n // align) * align
    return bytes(out)


def r_end(b):
    """End of the ITOC in a whole CPK b, for read_toc."""
    r = cpk.Utf(b, 0x10).rows[0]
    return r["ItocOffset"] + r["ItocSize"]


def unlayla(c):
    """CRILAYLA decompress: bytes from the end of the data, backwards; 0x100-byte raw prefix after it."""
    assert c[:8] == b"CRILAYLA"
    usize, hsize = struct.unpack_from("<II", c, 8)
    out = bytearray(usize + 0x100)
    out[:0x100] = c[0x10 + hsize:0x10 + hsize + 0x100]
    src, bit, bits = 0x10 + hsize - 1, 0, 0
    dst = usize + 0x100 - 1
    end = 0x100

    def take(n):
        nonlocal src, bit, bits
        v = 0
        while n:
            if bit == 0:
                bits, bit = c[src], 8
                src -= 1
            k = min(n, bit)
            v = (v << k) | ((bits >> (bit - k)) & ((1 << k) - 1))
            bit -= k
            n -= k
        return v

    while dst >= end:
        if take(1):
            off = take(13) + 3
            n = 3
            for w in (2, 3, 5, 8):
                v = take(w)
                n += v
                if v != (1 << w) - 1:
                    break
            else:
                while True:
                    v = take(8)
                    n += v
                    if v != 255:
                        break
            for _ in range(n):
                out[dst] = out[dst + off]
                dst -= 1
        else:
            out[dst] = take(8)
            dst -= 1
    return bytes(out)


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    with open(path, "rb") as f:
        b = f.read(0x8000)
        r, items = read_toc(b)
        if cmd == "list":
            for i in items:
                f.seek(i.off)
                print("%5d %10x %9d %9d %s" % (i.id, i.off, i.csize, i.size, f.read(16).hex()))
        elif cmd == "x":
            out = Path(sys.argv[3])
            out.mkdir(parents=True, exist_ok=True)
            for i in items:
                f.seek(i.off)
                d = f.read(i.csize)
                if d[:8] == b"CRILAYLA":
                    d = unlayla(d)
                (out / ("%05d.bin" % i.id)).write_bytes(d)
