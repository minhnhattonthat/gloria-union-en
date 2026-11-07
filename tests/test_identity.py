"""Identity build: unpack and repack with no edits gives the dump, byte for byte. Writer behaviour for real edits too."""
import hashlib
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
import cpk  # noqa: E402
import itoc  # noqa: E402
import pgd  # noqa: E402

pytestmark = pytest.mark.skipif(not build.ISO.exists(), reason="no dump in rom/")


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def dns():
    return build.read_dns()


def test_iso_identity(tmp_path):
    out = tmp_path / "identity.iso"
    build.rebuild(out, {})
    assert sha1(out) == (ROOT / "rom.sha1").read_text().splitlines()[-1].split()[0]


def test_pack_edits(dns):
    _, plain = dns
    grown, small, moved = bytes(70000), b"abc", b"x" * 0x10000
    new = itoc.pack(plain, {5: grown, 1: small, 6: moved})
    r, items = itoc.read_toc(new[:itoc.r_end(new)])
    assert len(items) == 2965 and [i.id for i in items] == list(range(2965))
    assert r["ContentOffset"] == 0x6800 and r["EnabledDataSize"] == sum(i.csize for i in items)
    assert r["EnabledPackedSize"] == sum(i.size for i in items)
    assert items[-1].off + items[-1].csize == len(new)
    assert (items[5].csize, items[5].size) == (70000, 70000)
    assert new[items[5].off:items[5].off + 70000] == grown
    assert new[items[1].off:items[1].off + 3] == small
    assert new[items[6].off:items[6].off + 0x10000] == moved
    _, old = itoc.read_toc(plain[:itoc.r_end(plain)])
    i, j = old[2964], items[2964]
    assert new[j.off:j.off + j.csize] == plain[i.off:i.off + i.csize]
    assert all(x.off % 2048 == 0 for x in items)


def test_pgd_build_reads_back(dns):
    head, _ = dns
    plain = bytes(range(256)) * 300 + b"tail"
    out = pgd.build(head, plain)
    p = pgd.parse(out[:0x90])
    assert p.mac80_ok and p.data_size == len(plain) and p.vkey == pgd.parse(head).vkey
    assert pgd.cipher(out[0x90:0x90 + p.align_size], p.key, 1)[:len(plain)] == plain
    table = out[p.table_offset:]
    assert len(table) == p.block_nr * 16
    assert pgd.mac_with(table, p.vkey) == out[0x60:0x70]
    assert struct.unpack_from("<I", p.desc, 0x14)[0] == len(plain)
    assert pgd.mac_with(out[0x90:0x490], p.vkey) == table[:16]
