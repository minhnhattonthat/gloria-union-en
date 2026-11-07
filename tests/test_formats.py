"""Format tests against the ROM; skipped when the dump is absent (a clone without the game)."""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import itoc  # noqa: E402
import pgd  # noqa: E402

ISO = ROOT / "rom" / "Gloria Union (Japan).iso"
DNS_LBA, DNS_SIZE = 61728, 424677840  # /PSP_GAME/INSDIR/DATA.DNS

pytestmark = pytest.mark.skipif(not ISO.exists(), reason="no dump in rom/")


@pytest.fixture(scope="module")
def dns():
    f = open(ISO, "rb")
    f.seek(DNS_LBA * 2048)
    head = f.read(0x90)
    yield pgd.parse(head), f
    f.close()


def read(p, f, off, n):
    """Plain bytes from DATA.DNS inside the ISO: pgd.decrypt with the file base applied."""
    a = off & ~15
    z = (off + n + 15) & ~15
    f.seek(DNS_LBA * 2048 + p.data_offset + a)
    return pgd.cipher(f.read(z - a), p.key, (a >> 4) + 1)[off - a:off - a + n]


def test_pgd_header(dns):
    p, _ = dns
    assert p.mac80_ok
    assert (p.data_size, p.block_size, p.data_offset) == (0x18EC5FB6, 0x400, 0x90)


def test_cpk_itoc(dns):
    p, f = dns
    head = read(p, f, 0, 0x8000)
    assert head[:4] == b"CPK "
    r, items = itoc.read_toc(head)
    assert len(items) == r["Files"] == 2965
    assert [i.id for i in items] == list(range(2965))
    # id order + 2048 alignment reach every file: the last one ends at the end of the data
    assert items[-1].off + items[-1].csize == p.data_size


def test_unlayla_size(dns):
    p, f = dns
    _, items = itoc.read_toc(read(p, f, 0, 0x8000))
    i = items[1]
    c = read(p, f, i.off, i.csize)
    assert c[:8] == b"CRILAYLA"
    d = itoc.unlayla(c)
    assert len(d) == i.size
    assert struct.unpack_from("<I", d, 4)[0] < 64
