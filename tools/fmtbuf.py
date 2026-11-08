"""Byte limits for EBOOT format strings that sprintf writes into stack buffers (the battle_result crash).

    python -X utf8 tools/fmtbuf.py            prints each %-string, its call, the buffer and its limit; writes tbl/fmtbuf.tsv

For each entry with a printf code and an `i:` (lui/lo) slot, the first `jal` within 12 instructions after the lo is
the call. If it is sprintf (0x14E3B0), its a0 is traced back to `addiu rX, $sp, OFF` in the same function; the
buffer ends at the next higher $sp offset the function uses (shortcut: stack layout heuristic; a larger local that
spans the gap would make the limit too small, never too large). Limit = buffer bytes - 1 for the NUL, for the
formatted output (numbers at their widest).
"""
import json
import re
import struct
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from extract import ELF  # noqa: E402
from insert import FMT, fmt_bytes  # noqa: E402

SPRINTF = 0x14E3B0
OFF = 0xA0   # file offset = vaddr + OFF in segment 0
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
md.detail = False
D = ELF.read_bytes()


def ins(va):
    return next(md.disasm(D[va + OFF:va + OFF + 4], va), None)


def func_start(va):
    """Walk back to the prologue `addiu $sp, $sp, -N`."""
    for a in range(va, va - 0x4000, -4):
        i = ins(a)
        if i and i.mnemonic == 'addiu' and i.op_str.startswith('$sp, $sp, -'): return a
    return None


def sp_offsets(start, end):
    """Every $sp offset the function at START uses, up to the next prologue or END (loads, stores, addiu rX, $sp, N)."""
    offs = set()
    for i in md.disasm(D[start + OFF:end + OFF], start):
        if i.address > start and i.mnemonic == 'addiu' and i.op_str.startswith('$sp, $sp, -'): break
        m = re.search(r'(-?0x[0-9a-f]+|\d+)\(\$sp\)', i.op_str)
        if m: offs.add(int(m.group(1), 0))
        m = re.match(r'\$\w+, \$sp, (0x[0-9a-f]+|\d+)$', i.op_str)
        if i.mnemonic == 'addiu' and m: offs.add(int(m.group(1), 0))
    return offs


def trace_a0(call, start):
    """$sp offset that a0 holds at CALL (delay slot included), or None."""
    reg = '$a0'
    for a in range(call + 4, start - 4, -4):
        i = ins(a)
        if not i: continue
        ops = [o.strip() for o in i.op_str.split(',')]
        if not ops or ops[0] != reg: continue
        if i.mnemonic == 'move': reg = ops[1]; continue
        if i.mnemonic == 'addiu' and ops[1] == '$sp': return int(ops[2], 0)
        if i.mnemonic in ('addu', 'or') and ops[2] == '$zero': reg = ops[1]; continue
        return None
    return None


def main():
    rows = []
    for p in sorted((ROOT / 'script/eboot').glob('*.json')):
        for e in json.loads(p.read_text('utf8')):
            if e['status'] == 'data' or not FMT.search(e['jp']): continue
            for s in e['slots']:
                if not s.startswith('i:'):
                    rows.append((e['id'], s, '', '', 'no lui/lo slot: not traced')); continue
                lo = int(s.split(':')[2], 16)
                jals = [a for a in range(lo - 4, lo + 96, 4) if (i := ins(a)) and i.mnemonic == 'jal']
                call = next((a for a in jals if int(ins(a).op_str, 0) == SPRINTF), None)
                if call is None:
                    rows.append((e['id'], s, ' '.join(ins(a).op_str for a in jals[:3]), '', 'no sprintf after it')); continue
                start = func_start(call)
                off = trace_a0(call, start) if start else None
                if off is None: rows.append((e['id'], s, 'sprintf', '', 'a0 not on the stack')); continue
                above = sorted(o for o in sp_offsets(start, start + 0x4000) if o > off)
                size = above[0] - off if above else None
                orig = fmt_bytes(e['jp'])
                if size and size - 1 < orig:   # the game's own text is longer, so the heuristic cut a real buffer
                    rows.append((e['id'], s, 'sprintf', f'sp+{off:#x}', f'{orig} (heuristic gave {size - 1}: original length)'))
                else:
                    rows.append((e['id'], s, 'sprintf', f'sp+{off:#x}', str(size - 1) if size else 'unknown'))
    # prefixes with no printf code (not found above): 0x40C1C-0x40C5C sprintf one of them into sp+0x44, then strcat
    # (0x14F170) the output of e:1ed9ac `%d％` (sp+0x5c) onto it: prefix + that output must fit sp+0x44's buffer
    start = func_start(0x40C24)
    above = sorted(o for o in sp_offsets(start, start + 0x4000) if o > 0x44)
    pct = next((int(r[4].split()[0]) for r in rows if r[0] == 'e:1ed9ac'), 5)
    for eid, s in (('e:1ed9a0', 'i:40c1c:40c28'), ('e:1ed9a4', 'i:40c3c:40c48'), ('e:1ed9a8', 'i:40c38:40c5c')):
        rows.append((eid, s, 'sprintf+strcat', 'sp+0x44', f'{above[0] - 0x44 - 1 - pct} (buffer minus e:1ed9ac output)'))
    out = ROOT / 'tbl' / 'fmtbuf.tsv'
    with out.open('w', encoding='utf8', newline='\n') as f:
        f.write('id\tslot\tcall\tbuffer\tmax_bytes\n')
        for r in rows: f.write('\t'.join(r) + '\n')
    for r in rows: print(*r, sep='\t')


if __name__ == '__main__':
    main()
