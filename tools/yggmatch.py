"""Textures shared with Yggdra Union (USA, same engine, official English): hash every PTX pixel block in
work/re/files and in Yggdra's data0.afs entries, print the byte-identical ones (palette ignored).

    python -X utf8 tools/yggmatch.py YGGDRA.iso

data0.afs: "AFS\\0", u32 count, count x (u32 offset, u32 size); an entry starting "ZLB\\0" is u32 raw size + zlib.
shortcut: exact pixel matches only; art that differs only in its text needs scoring outside the text boxes (phase 8)."""
import hashlib
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import iso9660
import ptx

ROOT = Path(__file__).resolve().parents[1]


def blocks(d):
    out = {}
    for t in ptx.scan(d):
        sz = ptx.stride(t) * t['h']
        px = d[t['do']:t['do'] + sz]
        if len(px) == sz and t['w'] * t['h'] >= 1024:
            out[hashlib.sha1(px).hexdigest()] = (t['off'], t['w'], t['h'])
    return out


def main(iso):
    g = {}
    for f in sorted((ROOT / 'work/re/files').glob('*.bin')):
        for h, v in blocks(f.read_bytes()).items():
            g.setdefault(h, (f.stem,) + v)
    with open(iso, 'rb') as f:
        lba = next(lba for p, lba, _, _ in iso9660.listing(f) if p == '/PSP_GAME/USRDIR/Data/data0.afs')
        f.seek(lba * 2048)
        assert f.read(4) == b'AFS\0'
        n = struct.unpack('<I', f.read(4))[0]
        tab = struct.unpack('<%dI' % (2 * n), f.read(8 * n))
        for i in range(n):
            f.seek(lba * 2048 + tab[2 * i])
            d = f.read(tab[2 * i + 1])
            if d[:4] == b'ZLB\0':
                d = zlib.decompress(d[8:])
            for h, (off, w, hh) in blocks(d).items():
                if h in g:
                    gid, goff, _, _ = g[h]
                    print(f'gloria {gid}@{goff:x}\tyggdra {i}@{off:x}\t{w}x{hh}')


if __name__ == '__main__':
    main(sys.argv[1])
