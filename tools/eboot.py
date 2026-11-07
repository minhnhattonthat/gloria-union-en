"""EBOOT patcher: code and data patches in segment 0, new code and data in a blob appended to segment 1.

    e = Eboot(plain_elf_bytes)
    e.put(0xA2648, asm('b 0xa26d4', 0xA2648), expect='...')   # in-place patch, original bytes asserted
    v = e.add(data)                                            # blob bytes; returns their vaddr
    code = e.code(src)                                         # assemble MIPS at the blob's end; j/jal get relocs
    out = e.build()

Layout (docs/re/text.md, EBOOT growth): segment 1 is .bss only (filesz 0x25C of .cplinit/.linkonce.d, memsz 0x9FBC5).
The build gives it file bytes for the whole .bss (zeros) plus the blob, so the blob loads at RAM base + vaddr like
everything else, and the relocation segment moves back by the growth. RAM = 0x8804000 + vaddr for both segments, so a
pointer to the blob is stored as its vaddr with address base 0, the same as every pointer into segment 0.
"""
import struct

import capstone
import keystone

SEG1 = 0x300588
RELOC_TYPES = {'R_MIPS_32': 2, 'R_MIPS_26': 4}
_ks = keystone.Ks(keystone.KS_ARCH_MIPS, keystone.KS_MODE_MIPS32 + keystone.KS_MODE_LITTLE_ENDIAN)
_cs = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)


def asm(src, vaddr):
    """Assemble at VADDR (absolute j/jal targets are vaddrs). Branch delay slots are written out by hand: keystone
    adds a nop after every jump unless told `.set noreorder`. Use named labels; `1f`/`1b` fail."""
    b, _ = _ks.asm('.set noreorder\n' + src, vaddr, as_bytes=True)
    assert b, 'keystone returned nothing'
    return b


def dis(b, vaddr):
    return [(i.address, i.mnemonic, i.op_str) for i in _cs.disasm(b, vaddr)]


class Eboot:
    def __init__(self, plain):
        self.d = bytearray(plain)
        self.orig = bytes(plain)
        e = struct.unpack_from('<16sHHIIIIIHHHHHH', plain, 0)
        assert e[1] == 0xFFA0 and e[10] == 3, 'expected the plain PRX with 3 program headers'
        self.phoff, self.shoff, self.shnum = e[5], e[6], e[12]
        self.ph = [list(struct.unpack_from('<8I', plain, self.phoff + i * 32)) for i in range(3)]
        assert self.ph[1][2] == SEG1 and self.ph[2][0] == 0x700000A0
        self.bss_end = SEG1 + self.ph[1][5]
        self.base = (self.bss_end + 0xF) & ~0xF   # blob vaddr
        self.blob = bytearray()
        off, size = self.ph[2][1], self.ph[2][4]
        self.relocs = [struct.unpack_from('<II', plain, off + i) for i in range(0, size, 8)]
        seg = [self.ph[0][2], self.ph[1][2]]
        self.has = {(seg[(info >> 8) & 0xFF] + o, info & 0xFF) for o, info in self.relocs}
        self.new_relocs = []
        self.log = []

    # segment 0 ------------------------------------------------------------------------------------------------
    def put(self, vaddr, data, expect=None, by=''):
        """Write DATA at VADDR in segment 0. EXPECT (bytes or hex) must be what the original holds there."""
        f = vaddr + 0xA0
        old = self.orig[f:f + len(data)]
        if expect is not None:
            exp = bytes.fromhex(expect) if isinstance(expect, str) else expect
            assert old == exp, f'{vaddr:#x}: original holds {old.hex()}, expected {exp.hex()} ({by})'
        assert vaddr + len(data) <= self.ph[0][4]
        self.log.append(f'{f:X} {old.hex()} {bytes(data).hex()} {by}')
        self.d[f:f + len(data)] = data

    def word(self, vaddr):
        return struct.unpack_from('<I', self.d, vaddr + 0xA0)[0]

    def reloc(self, vaddr, kind='R_MIPS_26'):
        """Make sure the word at VADDR is relocated (address base 0)."""
        t = RELOC_TYPES[kind]
        if (vaddr, t) in self.has: return
        self.has.add((vaddr, t))
        if vaddr >= SEG1: self.new_relocs.append((vaddr - SEG1, t | (1 << 8)))
        else: self.new_relocs.append((vaddr, t))

    def jal(self, site, target, expect=None, by='', op='jal'):
        """Write `jal TARGET` (or j) over the instruction at SITE in segment 0, with its relocation."""
        self.put(site, asm(f'{op} {target:#x}', site), expect, by)
        self.reloc(site)

    # blob -----------------------------------------------------------------------------------------------------
    def here(self):
        return self.base + len(self.blob)

    def align(self, n=4):
        self.blob += bytes(-len(self.blob) % n)

    def add(self, data, align=4):
        self.align(align)
        v = self.here()
        self.blob += data
        return v

    def code(self, src):
        """Assemble SRC at the blob's end. Every j/jal in it gets a relocation. Returns its vaddr.
        Code here is otherwise position independent: reach blob data with `bal` (see vwf.py)."""
        self.align(4)
        v = self.here()
        b = asm(src, v)
        for a, m, _ in dis(b, v):
            if m in ('j', 'jal'): self.reloc(a)
        assert len(dis(b, v)) * 4 == len(b), 'capstone could not read back all of the assembled code'
        self.blob += b
        return v

    def build(self):
        d = self.d
        ph = [p[:] for p in self.ph]
        seg1_off = ph[1][1]
        seg1 = bytearray(d[seg1_off:seg1_off + ph[1][4]])   # .cplinit/.linkonce.d bytes
        if self.blob:
            seg1 += bytes(self.base - SEG1 - len(seg1)) + self.blob
            ph[1][4] = ph[1][5] = len(seg1)
        rel_off = (seg1_off + len(seg1) + 0xF) & ~0xF
        relocs = d[ph[2][1]:ph[2][1] + ph[2][4]] + b''.join(struct.pack('<II', *r) for r in self.new_relocs)
        tail_old = ph[2][1] + ph[2][4]          # .shstrtab and the section headers follow the relocations
        delta = rel_off + len(relocs) - tail_old
        out = bytearray(d[:seg1_off]) + seg1
        out += bytes(rel_off - len(out)) + relocs
        out += d[tail_old:self.shoff]
        sh_at = len(out)
        out += d[self.shoff:]
        old_rel = ph[2][1]
        ph[2][1], ph[2][4] = rel_off, len(relocs)
        for i, p in enumerate(ph): struct.pack_into('<8I', out, self.phoff + i * 32, *p)
        struct.pack_into('<I', out, 0x20, sh_at)
        # PPSSPP applies the .rel sections when there are any, not the relocation segment: new entries go at the end
        # of the last one (.rel.linkonce.d), so both views hold them
        for i in range(self.shnum):
            o = sh_at + i * 40
            s_type, s_off, s_size = struct.unpack_from('<I', out, o + 4)[0], *struct.unpack_from('<II', out, o + 16)
            if s_type == 0x700000A0:
                if s_off + s_size == tail_old: s_size += len(self.new_relocs) * 8
                s_off += rel_off - old_rel
            elif s_off >= tail_old: s_off += delta
            struct.pack_into('<II', out, o + 16, s_off, s_size)
        return bytes(out)


def _selftest():
    import sys
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / 'work' / 're' / 'eboot.elf'
    if not p.exists(): return
    d = p.read_bytes()
    assert Eboot(d).build() == d, 'no edits must give the original'
    e = Eboot(d)
    v = e.code('jal 0xa20e4\nnop\njr $ra\nnop')
    assert (v - SEG1, 4 | 256) in e.new_relocs
    out = e.build()
    assert len(out) > len(d) and out[:0x300588 + 0xA0][0x100:] == d[0x100:0x300588 + 0xA0]
    print('eboot selftest ok', file=sys.stderr)


if __name__ == '__main__':
    _selftest()
