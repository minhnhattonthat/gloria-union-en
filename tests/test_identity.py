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


@pytest.mark.skipif(not (ROOT / "work/re/eboot.elf").exists(), reason="no work/re/eboot.elf")
def test_en_iso_writes_only_its_files(tmp_path):
    """The English ISO changes DATA.DNS and EBOOT.BIN and nothing else: every other file keeps its extent and bytes,
    and no sector changes outside those two files' old and new extents, the PVD and their directory records."""
    import iso9660
    out = build.build(tmp_path / "en.iso")
    with open(build.ISO, "rb") as a, open(out, "rb") as b:
        old = {p: (lba, ln, pos) for p, lba, ln, pos in iso9660.listing(a)}
        new = {p: (lba, ln, pos) for p, lba, ln, pos in iso9660.listing(b)}
        changed = {build.DNS, build.EBOOT}
        assert old.keys() == new.keys()
        assert all(old[p][:2] == new[p][:2] for p in old if p not in changed)
        ok = {16} | {old[p][2] // 2048 for p in changed}
        for p in changed:
            for lba, ln, _ in (old[p], new[p]):
                ok |= set(range(lba, lba + -(-ln // 2048)))
        bad, step, i = [], 2048 * 512, 0
        a.seek(0), b.seek(0)
        while True:
            x, y = a.read(step), b.read(step)
            if not y:
                break
            bad += [i + k for k in range(-(-len(y) // 2048))
                    if x[k * 2048:(k + 1) * 2048] != y[k * 2048:(k + 1) * 2048] and i + k not in ok]
            i += step // 2048
    assert not bad, bad[:20]


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
