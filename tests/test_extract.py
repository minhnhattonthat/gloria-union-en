"""Phase 4: every extracted string re-encodes to the original bytes, and no text sits outside script/.
Reads work/re (AGENTS.md, Unpack); skipped on a clone without it."""
import json
import re
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import elf  # noqa: E402
import extract  # noqa: E402
import vm  # noqa: E402

pytestmark = pytest.mark.skipif(not extract.ELF.exists(), reason="no work/re")
KANA = re.compile("[぀-ヿ]")
# Runs in the EBOOT with 2+ kana or 3+ kanji and no entry: read by eye, all binary.
EBOOT_NOT_TEXT = {0x265361, 0x2679FF, 0x26A5DB, 0x2822C1, 0x2896E1, 0x290641, 0x292CDF, 0x2958BB, 0x2BC380, 0x2C34AB, 0x2D7E7E,
                  0x2DEC5B}


def load(name):
    return json.loads((extract.OUT / name).read_text("utf8"))


def sources():
    """(json name, id prefix, file bytes, spans) for every script-like block."""
    for i in extract.STORY:
        b = (extract.FILES / f"{i:05d}.bin").read_bytes()
        yield f"story/{i}.json", b, vm.parse(b)
    sec = extract.fct((extract.FILES / "00003.bin").read_bytes(), extract.SUBS[1])
    for n in extract.SUB_TEXT:
        if n not in extract.BARE:
            b = extract.fct(sec, n)
            yield f"common/sub{n}.json", b, extract.sub_spans(b, n)


@pytest.fixture(scope="module")
def blocks():
    return list(sources())


def test_codec():
    for s in ("a\nb", "x[0A]y", "全角　\n[0A]"):
        assert extract.to_text(extract.from_text(s)) == s


def test_spans_cover_every_byte(blocks):
    for _, b, spans in blocks:
        assert all(a.end == c.off for a, c in zip(spans, spans[1:])) and spans[-1].end == len(b)


def test_script_text_roundtrips_and_slots_point_home(blocks):
    for name, b, spans in blocks:
        by_off = {int(e["id"].split(":")[1].rstrip("t"), 16): e for e in load(name)}
        texts = [s for s in spans if s.kind == "text"]
        for s in texts:
            e = by_off[s.off]
            tag = struct.pack("<HH", 2, e["voice"]) if "voice" in e else b""
            assert tag + extract.from_text(e["jp"]) + b"\0" == b[s.off:s.end], e["id"]
            for slot in e["slots"]:
                assert struct.unpack_from("<I", b, int(slot, 16))[0] == s.off
        names = [s for s in spans if s.kind == "op" and s.op == 0x74]
        assert len(by_off) == len(texts) + len(names), name
        for s in names:
            e = by_off[s.off]
            assert b[s.off + 3:s.end] == extract.from_text(e["jp"]) + b"\0" and e["max"] == s.end - s.off - 4


def test_every_show_targets_text(blocks):
    for name, b, spans in blocks:
        texts = {s.off for s in spans if s.kind == "text"}
        shows = {struct.unpack_from("<I", b, s.off + 3)[0] for s in spans if s.kind == "op" and s.op == 0x46 and b[s.off + 1] == 7}
        assert shows <= texts, name


def test_no_text_hiding_in_code(blocks):
    run = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){3,}")
    for name, b, spans in blocks:
        for s in spans:
            if s.kind in ("op", "table") and s.op != 0x74:
                for m in run.finditer(b[s.off:s.end]):
                    try:
                        assert not KANA.search(m.group().decode("cp932")), (name, hex(s.off))
                    except UnicodeDecodeError:
                        pass


def test_bare_subs_roundtrip():
    sec = extract.fct((extract.FILES / "00003.bin").read_bytes(), extract.SUBS[1])
    for n in extract.BARE:
        b = extract.fct(sec, n)
        assert b"".join(extract.from_text(e["jp"]) + b"\0" for e in load(f"common/sub{n}.json")) == b


def test_eboot_roundtrip_and_refs():
    d = extract.ELF.read_bytes()
    seen = bytearray(len(d))
    for f in (extract.OUT / "eboot").glob("*.json"):
        for e in json.loads(f.read_text("utf8")):
            a = int(e["id"][2:], 16)
            raw = extract.from_text(e["jp"])
            assert d[a + elf.OFF:a + elf.OFF + len(raw) + 1] == raw + b"\0", e["id"]
            seen[a + elf.OFF:a + elf.OFF + len(raw)] = b"\1" * len(raw)
            assert e["slots"], e["id"]
            for slot in e["slots"]:
                if slot[0] == "w":
                    assert struct.unpack_from("<I", d, int(slot[2:], 16) + elf.OFF)[0] == a, e["id"]
                else:
                    hi, lo = (struct.unpack_from("<I", d, int(x, 16) + elf.OFF)[0] for x in slot[2:].split(":"))
                    assert ((hi & 0xFFFF) << 16) + struct.unpack("<h", struct.pack("<H", lo & 0xFFFF))[0] == a, e["id"]
    left = []
    for a, raw in elf.runs(d, elf.RODATA, elf.DATA_END):
        if seen[a + elf.OFF:a + elf.OFF + len(raw)].count(1) == len(raw):
            continue
        try:
            u = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        if len(KANA.findall(u)) >= 2 or len(re.findall("[一-鿿]", u)) >= 3:
            left.append(a)
    assert set(left) == EBOOT_NOT_TEXT, [hex(x) for x in left]


def test_dump_does_not_clobber():
    """extract.py's guard: script/ exists, so a plain run must refuse."""
    import subprocess
    r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools/extract.py")], capture_output=True, text=True)
    assert r.returncode != 0 and "overwrite" in r.stderr
