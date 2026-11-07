"""EBOOT lookups over work/re/eboot.elf and eboot.asm (tools/mkasm.py). Run from the repo root.

    python -X utf8 tools/refind.py str 'スキルは使えません'    Shift-JIS text: where it is, pointers to it, code that builds its address
    python -X utf8 tools/refind.py jt 0x131008 0x133600       jump tables (lui/addu/lw/jr $at) used in a code range
"""
import re
import struct
import sys

ELF, ASM, OFF = 'work/re/eboot.elf', 'work/re/eboot.asm', 0xA0   # file offset = vaddr + OFF
d = open(ELF, 'rb').read()
L = open(ASM).read().split('\n')


def find_str(text):
    for m in re.finditer(re.escape(text.encode('cp932')), d):
        st = m.start() - OFF
        while d[st + OFF - 1]: st -= 1
        print(hex(st), d[st + OFF:d.index(b'\0', st + OFF)].decode('cp932', 'replace'))
        for p in re.finditer(re.escape(struct.pack('<I', st)), d): print('    ptr at', hex(p.start() - OFF))
        hi, lo = (st + 0x8000) >> 16, st & 0xffff
        lo = f'-{0x10000 - lo:#x}' if lo >= 0x8000 else f'{lo:#x}'
        for i, line in enumerate(L):
            if re.search(rf'(addiu|ori) \S+, \S+, {lo}$', line) and any('lui' in x and x.endswith(f', {hi:#x}') for x in L[max(0, i - 12):i]):
                print('   ', line)


def jump_tables(a, b):
    for i in range(a // 4, b // 4):
        if 'jr $at' not in L[i]: continue
        hi = re.search(r'lui \$at, (\S+)', L[i - 4]); lo = re.search(r'lw \$at, (\S+)\(\$at\)', L[i - 2])
        if not hi or not lo: continue
        t = (int(hi[1], 16) << 16) + int(lo[1], 16)
        out = []
        while len(out) < 300:
            v = struct.unpack_from('<I', d, t + OFF + len(out) * 4)[0]
            if not a - 0x8000 <= v < b + 0x8000: break
            out.append(f'{len(out):x}:{v:x}')
        print(L[i], 'table', hex(t), ' '.join(out))


if sys.argv[1] == 'str': find_str(sys.argv[2])
else: jump_tables(int(sys.argv[2], 16), int(sys.argv[3], 16))
