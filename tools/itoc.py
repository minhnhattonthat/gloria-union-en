"""CPK with an ITOC only (files by id, no names): list and read.

    python -X utf8 tools/itoc.py list work/re/data.bin
    python -X utf8 tools/itoc.py x work/re/data.bin OUTDIR     # one file per id, CRILAYLA expanded

Entries in id order, each at the next Align boundary from ContentOffset (checked by test_itoc).
"""
import struct
import sys
from collections import namedtuple
from pathlib import Path

from skill import SCRIPTS

sys.path.insert(0, SCRIPTS)
import cpk  # noqa: E402

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
