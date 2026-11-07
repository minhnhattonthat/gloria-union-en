import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import eboot  # noqa: E402


def test_eboot_rebuild():
    """No edits give the original ELF; a blob jal gets its relocation (skips without work/re/eboot.elf)."""
    eboot._selftest()


def test_asm_noreorder():
    assert len(eboot.asm('j 0xa3c64', 0x3A0150)) == 4
