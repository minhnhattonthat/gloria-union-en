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


if __name__ == "__main__":
    import subprocess
    subprocess.check_call([sys.executable, "-X", "utf8", str(ROOT / "tools" / "check_rom.py")])
    rebuild(OUT, {})
    print(OUT)
