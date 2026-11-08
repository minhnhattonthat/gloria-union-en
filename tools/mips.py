"""MIPS disassembly of the EBOOT by vaddr (work/re/eboot.elf, segment 0 at vaddr 0), and jal callers.

    python -X utf8 tools/dis.py ADDR [COUNT]       e.g. tools/dis.py a3d60 40
    python -X utf8 tools/dis.py --callers ADDR

The skill's disasm.py takes raw files: on the ELF its addresses are file offsets, not vaddrs.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN


def code(path='work/re/eboot.elf'):
    raw = open(path, 'rb').read()
    phoff = struct.unpack_from('<I', raw, 0x1C)[0]
    off, vaddr, _, size = struct.unpack_from('<IIII', raw, phoff + 4)
    assert vaddr == 0
    return raw[off:off + size]


def dis(addr, count=40, c=None):
    c = c or code()
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    return [f'{i.address:06x} {i.mnemonic} {i.op_str}' for i in md.disasm(c[addr:addr + 4 * count], addr)]


def callers(target, c=None):
    c = c or code()
    w = 0x0C000000 | (target >> 2)
    return [i for i in range(0, len(c), 4) if struct.unpack_from('<I', c, i)[0] == w]


if __name__ == '__main__':
    if sys.argv[1] == '--callers':
        print(' '.join(hex(a) for a in callers(int(sys.argv[2], 16))))
    else:
        print('\n'.join(dis(int(sys.argv[1], 16), int(sys.argv[2]) if len(sys.argv) > 2 else 40)))
