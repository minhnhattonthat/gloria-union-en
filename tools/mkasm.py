"""Disassemble .text of work/re/eboot.elf to work/re/eboot.asm, one `vaddr  insn` per line (for grep; vaddr = file - 0xA0)."""
import capstone

data = open('work/re/eboot.elf', 'rb').read()
text = data[0xA0:0xA0 + 0x1C947C]
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
md.skipdata = True
with open('work/re/eboot.asm', 'w') as f:
    for a, _, m, o in md.disasm_lite(text, 0):
        f.write(f'{a:06x} {m} {o}\n')
