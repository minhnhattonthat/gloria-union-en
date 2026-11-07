"""One-off proof that text lives where docs/re/text.md says: scan every expanded CPK file for sentence-like runs.

    python -X utf8 tools/textsweep.py     prints file, encoding, bytes, first hit, for files outside the known text ids

A hit: NUL-terminated cp932 with 3+ kana and kana >= half the kanji, or the same test on UTF-8 and UTF-16LE. Audio is skipped.
"""
import re
import sys
from pathlib import Path

FILES = Path("work/re/files")
KNOWN = set(range(2032, 2083)) | {3}
AUDIO = (b"RIFF", b"\x80\x00\x00$", b"\x80\x00\x07\xfc", b"VPD\0")
SJIS = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x01\n]){3,}\x00")
UTF8 = re.compile(rb"(?:[\xe3-\xe9][\x80-\xbf][\x80-\xbf]|[\x20-\x7e\n]){3,}\x00")
UTF16 = re.compile(rb"(?:[\x00-\xff][\x30-\x9f]|[\x20-\x7e]\x00){3,}\x00\x00")


def sentence(s):
    kana = sum(0x3040 <= ord(c) <= 0x30FF for c in s)
    return kana >= 3 and kana * 2 >= sum(0x4E00 <= ord(c) <= 0x9FFF for c in s)


def hits(d):
    for name, rx, enc, tail in (("cp932", SJIS, "cp932", 1), ("utf8", UTF8, "utf8", 1), ("utf16", UTF16, "utf-16le", 2)):
        n, first = 0, None
        for m in rx.finditer(d):
            try:
                s = m.group()[:-tail].decode(enc)
            except UnicodeDecodeError:
                continue
            if sentence(s):
                n += len(m.group())
                first = first or s[:30]
        if n:
            yield name, n, first


for f in sorted(FILES.glob("*.bin")):
    i = int(f.stem)
    d = f.read_bytes()
    if i in KNOWN or d[:4] in AUDIO or (d[:4] == b"FCT\0" and b"(c)CRI" in d[:0x1000]):
        continue
    for name, n, first in hits(d):
        print(i, d[:4], name, n, repr(first), flush=True)
