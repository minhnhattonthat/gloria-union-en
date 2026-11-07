"""PGD (PSP DNAS container, DATA.DNS) read and rewrite, ported from PPSSPP ext/libkirk/amctrl.c.

    python -X utf8 tools/pgd.py x IN OUT     # decrypt
Library: parse(buf) -> Pgd; Pgd.decrypt(buf, off, size); Pgd.encrypt_bytes(plain, off)

Only drm_type 1, key_index 1 is handled (mac type 1, cipher type 1): the one form in this game.
"""
import struct
import sys

import numpy as np
from Crypto.Cipher import AES
from Crypto.Hash import CMAC

KEY38 = bytes.fromhex("12468D7E1C42209BBA5426835EB03303")
KEY39 = bytes.fromhex("C43BB6D653EE67493EA95FBC0CED6F8A")
KEY63 = bytes.fromhex("9C9B1372F8C640CF1C62F5D592DDB582")
LOC_CD4 = bytes.fromhex("E350ED1D910A1FD029BB1C3EF34077FB")
LOC_CE4 = bytes.fromhex("135FA47CAB395BA476B8CCA98F3A0445")
LOC_CF4 = bytes.fromhex("678D7FA32A9CA0D1508AD8385E4B017E")
FKEY = bytes.fromhex("EDE25D2DBBF812E53C5C5932FAE3E243")  # dnas_key1A90, pgd_flag 2


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def d(key, data):
    return AES.new(key, AES.MODE_CBC, iv=bytes(16)).decrypt(data)


def e(key, data):
    return AES.new(key, AES.MODE_CBC, iv=bytes(16)).encrypt(data)


def bbmac(data):
    """sceDrmBBMacFinal with vkey NULL: AES-CMAC under KIRK key 0x38, then the fixed xor."""
    return xor(CMAC.new(KEY38, data, ciphermod=AES).digest(), LOC_CD4)


def mac_with(data, vkey):
    return e(KEY38, xor(bbmac(data), vkey))


def vkey_from(data, mac):
    return xor(bbmac(data), d(KEY38, mac))


def keystream(key, seed, size):
    """sub_428 for `size` bytes (a multiple of 16) starting at counter `seed`.
    The counters are CBC-decrypted with the previous counter as IV, so the stream is seekable."""
    base = xor(d(KEY39, xor(key, LOC_CF4)), LOC_CE4)
    n = size // 16
    blocks = np.frombuffer(base[:12] + b"\0\0\0\0", dtype="<u4").reshape(1, 4).repeat(n + 1, axis=0).copy()
    blocks[:, 3] = np.arange(seed - 1, seed + n, dtype=np.uint64) & 0xFFFFFFFF
    raw = blocks.tobytes()
    iv = bytes(16) if seed == 1 else raw[:16]
    return AES.new(KEY63, AES.MODE_CBC, iv=iv).decrypt(raw[16:])


def cipher(data, key, seed):
    if not data:
        return b""
    ks = keystream(key, seed, -(-len(data) // 16) * 16)
    a = np.frombuffer(data, dtype=np.uint8)
    b = np.frombuffer(ks, dtype=np.uint8, count=len(data))
    return (a ^ b).tobytes()


class Pgd:
    pass


def parse(buf):
    assert buf[:4] == b"\0PGD", "not a PGD"
    p = Pgd()
    p.key_index, p.drm_type = struct.unpack_from("<II", buf, 4)
    assert (p.key_index, p.drm_type) == (1, 1), (p.key_index, p.drm_type)
    p.mac80_ok = mac_with(buf[:0x80], FKEY) == buf[0x80:0x90]
    p.vkey = vkey_from(buf[:0x70], buf[0x70:0x80])
    hk = xor(buf[0x10:0x20], p.vkey)
    desc = cipher(bytes(buf[0x30:0x60]), hk, 1)
    p.desc = desc
    p.dkey = desc[:16]
    p.ver, p.data_size, p.block_size, p.data_offset = struct.unpack_from("<IIII", desc, 0x10)
    p.key = xor(p.dkey, p.vkey)
    p.align_size = (p.data_size + 15) & ~15
    p.table_offset = p.data_offset + p.align_size
    p.block_nr = (p.align_size + p.block_size - 1) // p.block_size
    return p


def decrypt(p, f, off, size):
    """`size` plain bytes at plain offset `off`, from file object f."""
    a = off & ~15
    z = (off + size + 15) & ~15
    f.seek(p.data_offset + a)
    return cipher(f.read(z - a), p.key, (a >> 4) + 1)[off - a:off - a + size]


if __name__ == "__main__":
    cmd, src = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        head = f.read(0x90)
        p = parse(head)
        print("data_size %#x block %#x data_off %#x blocks %d mac80 %s vkey %s" % (
            p.data_size, p.block_size, p.data_offset, p.block_nr, p.mac80_ok, p.vkey.hex()))
        if cmd == "x":
            with open(sys.argv[3], "wb") as o:
                for off in range(0, p.data_size, 1 << 24):
                    o.write(decrypt(p, f, off, min(1 << 24, p.data_size - off)))
