"""build.py: rom/ ISO -> build/gloria_en.iso: decrypt DATA.DNS, rebuild the CPK and the PGD, patch the ISO.

    python -X utf8 build.py

With no edits the result is byte-identical to the dump (tests/test_identity.py).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import iso9660  # noqa: E402
import itoc  # noqa: E402
import pgd  # noqa: E402

ISO = ROOT / "rom" / "Gloria Union (Japan).iso"
OUT = ROOT / "build" / "gloria_en.iso"
DNS = "/PSP_GAME/INSDIR/DATA.DNS"


def read_dns():
    """(PGD header, plain CPK) from the dump."""
    with open(ISO, "rb") as f:
        lba, size = next((x[1], x[2]) for x in iso9660.listing(f) if x[0] == DNS)
        f.seek(lba * 2048)
        head = f.read(0x90)
        p = pgd.parse(head)
        step = 1 << 24
        plain = bytearray(p.data_size)
        for off in range(0, p.data_size, step):
            n = min(step, p.data_size - off)
            f.seek(lba * 2048 + p.data_offset + off)
            plain[off:off + n] = pgd.cipher(f.read(-(-n // 16) * 16), p.key, (off >> 4) + 1)[:n]
    return head, bytes(plain)


def rebuild(out, repl, files=None):
    """Write the ISO to `out`, with `repl` {CPK id: file bytes} replaced, and `files` {ISO path: bytes} (EBOOT)."""
    head, plain = read_dns()
    out.parent.mkdir(exist_ok=True)
    iso9660.patch(str(ISO), str(out), {DNS: pgd.build(head, itoc.pack(plain, repl)), **(files or {})})


EBOOT = "/PSP_GAME/SYSDIR/EBOOT.BIN"


def build(out, mode="en", only=None, qa=None):
    """VWF + text from script/ ('en': English where present; 'marker': every line marked, tools/insert.py).
    qa: {entry id: text} overrides, for width tests."""
    import gfx
    import insert
    ins = insert.Inserter(mode, only, qa)
    files = {EBOOT: ins.eboot()}
    rebuild(out, gfx.apply(ins.cpk()), files)
    log = out.with_suffix(".writes.txt")
    log.write_text("\n".join(ins.eb.log) + "\n", "utf8")
    return out


if __name__ == "__main__":
    import argparse
    import subprocess
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--marker", action="store_true", help="every line as [id] + filler: build/gloria_marker.iso")
    ap.add_argument("--only", nargs="*", help="id prefixes to change (e.g. s2034 e:2b); others stay original")
    ap.add_argument("--plain", action="store_true", help="no edits at all: the identity build")
    ap.add_argument("--qa", nargs="*", default=[], help="ID=TEXT overrides (\\n in TEXT is a line break)")
    ap.add_argument("--qa-file", help="TSV of ID<tab>TEXT overrides, same escapes as --qa (tools/stress.py --fit)")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    if a.qa_file:
        a.qa += [ln.replace("\t", "=", 1) for ln in Path(a.qa_file).read_text("utf8").splitlines() if ln]
    subprocess.check_call([sys.executable, "-X", "utf8", str(ROOT / "tools" / "check_rom.py")])
    out = Path(a.out) if a.out else ROOT / "build" / ("gloria_marker.iso" if a.marker else "gloria_en.iso")
    if a.plain:
        rebuild(out, {})
    else:
        qa = dict(x.split("=", 1) for x in a.qa)
        build(out, "marker" if a.marker else "en", a.only, {k: v.replace("\\n", "\n") for k, v in qa.items()})
    print(out)
