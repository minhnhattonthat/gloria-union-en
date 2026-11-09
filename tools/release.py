"""release.py: build, gate and package the English patch (references/pipeline.md §Release in the skill).

    python -X utf8 tools/release.py [--version 1.0] [--force] [--skip-build]

Stops at the first failure: build -> tools/check.py -> smoke boot -> no unintended Japanese (EBOOT scan + drawn text
of the final tour) -> qa_gate.py check on every work/qa/**/manifest.tsv -> textcover.py -> no unticked line in
docs/polish.md -> no template placeholder in README.md -> no debug/marker/QA writes in the build -> xdelta3 patch ->
re-apply to the original and compare -> release/Gloria_Union_EN_v<version>.zip (patch + README.txt, ZIP_STORED).
Refuses to overwrite an existing version's files without --force. Never publishes: that is the owner's call.
"""
import argparse
import bisect
import glob
import hashlib
import json
import re
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from skill import SKILL  # noqa: E402

ISO = ROOT / "rom" / "Gloria Union (Japan).iso"
BUILT = ROOT / "build" / "gloria_en.iso"
EBOOT = "/PSP_GAME/SYSDIR/EBOOT.BIN"
ORIG_ELF = ROOT / "work" / "re" / "eboot.elf"  # PPSSPP's decrypted dump of the original EBOOT (status.md item 4)
ELF_HEAD = 0xA0  # e:<id> = ELF file offset - 0xA0
# jp_left runs in the EBOOT that no script entry covers: all binary data that happens to decode as Shift-JIS
# (checked session 50). A new offset here means an extractor blind spot: look before adding it.
NOISE = {0x26943B, 0x26A69E, 0x26AC42, 0x26AE7A, 0x26C67F, 0x26C811, 0x29471B, 0x29597E, 0x295F22, 0x29615A,
         0x29795F, 0x297AF1, 0x2AF230, 0x2ED330}
PLACEHOLDER = re.compile(r"<(Game title|platform|publisher|year|repo|file|size|sha1|game|ext|none known)[^>]*>")
PY = [sys.executable, "-X", "utf8"]


def step(name, ok, detail=""):
    print(f"[{'ok' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}", flush=True)
    if not ok:
        sys.exit(1)


def run(*cmd):
    return subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, encoding="utf8",
                          errors="replace")


def hashes(path):
    h = {"md5": hashlib.md5(), "sha1": hashlib.sha1()}
    crc = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 24):
            crc = zlib.crc32(chunk, crc)
            for x in h.values():
                x.update(chunk)
    return {"size": path.stat().st_size, "crc32": f"{crc:08x}", **{k: v.hexdigest() for k, v in h.items()}}


def iso_file(iso, path):
    import iso9660
    with open(iso, "rb") as f:
        lba, size = next((x[1], x[2]) for x in iso9660.listing(f) if x[0] == path)
        f.seek(lba * 2048)
        return f.read(size)


def jp_eboot(tmp):
    """Japanese runs in the built EBOOT that are unchanged from the original and lie in no script entry."""
    elf = tmp / "eboot_en.elf"
    elf.write_bytes(iso_file(BUILT, EBOOT))
    r = run(*PY, Path(SKILL) / "scripts" / "jp_left.py", elf, "--sjis", "--orig", ORIG_ELF, "--limit", "1000000")
    starts = sorted(int(e["id"][2:], 16) + ELF_HEAD for f in glob.glob(str(ROOT / "script" / "eboot" / "*.json"))
                    for e in json.load(open(f, encoding="utf8")) if e["id"].startswith("e:"))
    left = []
    for ln in r.stdout.splitlines():
        m = re.match(r"0x([0-9A-F]+)\s+\d+B", ln)
        if not m:
            continue
        off = int(m[1], 16)
        i = bisect.bisect_right(starts, off) - 1
        inside = i >= 0 and off - starts[i] < 512  # relocated string: its old Japanese stays, unreferenced
        if not inside and off not in NOISE:
            left.append(ln)
    return left


def untranslated():
    """Script entries with Japanese and no English, other than data/debug ('data') and blank pads ('todo', all
    U+3000 or spaces)."""
    bad = []
    for f in glob.glob(str(ROOT / "script" / "**" / "*.json"), recursive=True):
        for e in json.load(open(f, encoding="utf8")):
            if not e.get("en") and e.get("status") != "data" and e["jp"].strip("　 \n"):
                bad.append(e["id"])
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--force", action="store_true", help="overwrite this version's release files")
    ap.add_argument("--skip-build", action="store_true", help="gate and package the existing build/gloria_en.iso")
    a = ap.parse_args()

    rel = ROOT / "release"
    name = f"Gloria_Union_EN_v{a.version}"
    patch, zpath = rel / f"{name}.xdelta", rel / f"{name}.zip"
    if not a.force and (patch.exists() or zpath.exists()):
        step("release files", False, f"{zpath.name} exists; pass --force to overwrite")
    rel.mkdir(exist_ok=True)
    tmp = ROOT / "work" / "release"
    tmp.mkdir(parents=True, exist_ok=True)

    # a gfx/text.tsv edit regenerated for one asset only left its twin stale (title1870v kept "Full Stop", session 51)
    r = run(*PY, ROOT / "tools" / "gfx.py", "gen")
    d = run("git", "status", "--porcelain", "--", "gfx")
    step("gfx/*.png match a fresh gfx.py gen", r.returncode == 0 and not d.stdout.strip(),
         d.stdout.strip() or r.stderr[-400:])
    if not a.skip_build:
        r = run(*PY, ROOT / "build.py")
        step("build", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-400:])
    r = run(*PY, ROOT / "tools" / "check.py")
    step("tests + lint", r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1])
    r = run(*PY, Path(SKILL) / "scripts" / "emu.py", BUILT, "--out", ROOT / "work" / "qa" / "smoke",
            "--route", ROOT / "tools" / "routes" / "boot.txt", "--smoke")
    step("smoke boot", r.returncode == 0, f"exit {r.returncode}")

    left = jp_eboot(tmp)
    step("EBOOT Japanese outside the script", not left, "\n  " + "\n  ".join(left[:20]) if left else "0 runs")
    bad = untranslated()
    step("script entries without English", not bad, ", ".join(bad[:20]) if bad else "0")
    r = run(*PY, ROOT / "tools" / "tour.py", "jp", ROOT / "work" / "qa" / "final")
    step("drawn Japanese on the final tour", r.returncode == 0, r.stderr.strip())

    for m in sorted(glob.glob(str(ROOT / "work" / "qa" / "**" / "manifest.tsv"), recursive=True)):
        v = Path(m).parent / "verdicts"
        r = run(*PY, Path(SKILL) / "scripts" / "qa_gate.py", "check", m, v)
        step(f"qa_gate {Path(m).relative_to(ROOT).as_posix()}", r.returncode == 0,
             (r.stdout + r.stderr).strip().splitlines()[-1])
    cover = ROOT / "work" / "qa" / "cover"
    r = run(*PY, Path(SKILL) / "scripts" / "textcover.py", cover, cover / "strings.tsv",
            "--waive", ROOT / "docs" / "text_unshown.tsv")
    step("textcover", r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1])

    open_lines = [ln for ln in (ROOT / "docs" / "polish.md").read_text("utf8").splitlines() if ln.startswith("- [ ]")]
    step("docs/polish.md all ticked", not open_lines, f"{len(open_lines)} open" if open_lines else "")
    readme = (ROOT / "README.md").read_text("utf8")
    ph = PLACEHOLDER.findall(readme)
    step("README.md has no template placeholder", not ph, ", ".join(ph))
    writes = (BUILT.with_suffix(".writes.txt")).read_text("utf8")
    dbg = [ln for ln in writes.splitlines() if re.search(r"debug|warp|marker|\bqa\b", ln, re.I)]
    step("no debug/marker/QA writes in the build", not dbg, dbg[0] if dbg else "warp is runtime-only (emulator)")

    base, built = hashes(ISO), hashes(BUILT)
    if patch.exists():
        patch.unlink()
    r = run("xdelta3", "-e", "-9", "-S", "djw", "-B", str(base["size"]), "-s", ISO, BUILT, patch)
    step("xdelta3 patch", r.returncode == 0, f"{patch.stat().st_size:,} bytes" if r.returncode == 0 else r.stderr)
    check = tmp / "reapplied.iso"
    r = run("xdelta3", "-d", "-f", "-B", str(base["size"]), "-s", ISO, patch, check)
    same = r.returncode == 0 and hashes(check)["sha1"] == built["sha1"]
    step("patch re-applied to the original = build", same, built["sha1"])
    check.unlink()

    txt = (ROOT / "docs" / "release-readme.txt").read_text("utf8")
    for k, v in {"VERSION": a.version, "PATCH": patch.name, "BASE_SIZE": f"{base['size']:,}",
                 "BASE_CRC32": base["crc32"], "BASE_MD5": base["md5"], "BASE_SHA1": base["sha1"],
                 "OUT_CRC32": built["crc32"], "OUT_SHA1": built["sha1"]}.items():
        txt = txt.replace("{" + k + "}", v)
    left_keys = re.findall(r"\{[A-Z_0-9]+\}", txt)
    step("zip README filled", not left_keys, ", ".join(left_keys))
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.write(patch, patch.name)
        z.writestr("README.txt", txt.replace("\n", "\r\n"))
    step("zip", True, f"{zpath.relative_to(ROOT).as_posix()} ({zpath.stat().st_size:,} bytes)")
    print(f"patched ISO: {BUILT.relative_to(ROOT).as_posix()} sha1 {built['sha1']} crc32 {built['crc32']}")
    print(f"base ISO: {base}")


if __name__ == "__main__":
    main()
