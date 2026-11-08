"""VWF for engine fonts 1-4: ASCII drawn from new glyph sheets in the EBOOT blob, placed at proportional x.

    import vwf; vwf.patch(eboot)                      # called from build.py
    python -X utf8 tools/vwf.py preview OUT.png       # the three sheets plus sample lines, as the engine spaces them

How it works (docs/re/text.md, Text renderer and VWF):
- The writer (0xA222C) maps ASCII in fonts 1-4 to glyph 0x8000 | c instead of the fullwidth lookup; the ligature
  checks (`!?`, `Lv`, ...) are skipped.
- Its three calls to the glyph setter go through `wrap`: an ASCII glyph gets u, v, size and texture from our sheet
  (a PTX in the blob, already in its loaded form) and its width; every glyph in fonts 1-4 then gets a pixel x in
  cell +0 (previous cell's x + advance; grid x when the previous cell is empty or not VWF) and flags in +1E:
  0x8000 = VWF, bits 8-13 = advance, 0x4000 = placed by `chain`. The writer's flag reset clears bits 8-15 too.
- The sprite builder uses +0 as x when 0x8000 is set (window x and offset still added), so windows can move.
- Menus that place each cell themselves (re-layout helper 0xA3D74, absolute bit 0) do it for the original column
  count at a fixed pitch: in the builder, `chain` puts a VWF cell right after an absolute VWF cell before it in the
  row (x = its x + advance) and gives cells the menu didn't place (or chain placed) its y too.
- setSize allocates 3x the columns, so a row holds about three times as many (narrow) characters.
"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / 'fonts' / 'MPLUSRounded1c-ExtraBold.ttf'

# engine font -> cell w, h, key (transparent index), outline index, fill index, cap height px, top of caps, italic
STYLE = {
    1: dict(cw=20, ch=20, key=0, edge=1, fill=14, cap=10, top=3, shear=0.0),    # dialogue: font A; ink in rows 2-17
    2: dict(cw=14, ch=16, key=15, edge=0, fill=14, cap=11, top=1, shear=0.0),   # font C, small
    3: dict(cw=24, ch=24, key=0, edge=1, fill=15, cap=14, top=4, shear=0.2),    # name tags: font B, italic
    4: dict(cw=12, ch=12, key=0, edge=2, fill=1, cap=8, top=2, shear=0.0),      # small battle font: white, black edge
}
PAGE = {1: (1, 2), 2: (5, 6), 3: (3, 4), 4: (0, None)}   # engine font -> (texture, index) sub of id 3 section 1
COLS = 16                                   # glyphs per sheet row; glyph c at ((c-0x20) % 16, (c-0x20) // 16)


def palette(font):
    """The font's own 16-colour palette (ABGR8888 bytes), from its first page."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import ptx
    from extract import fct
    b = (ROOT / 'work' / 're' / 'files' / '00003.bin').read_bytes()
    t = fct(fct(b, 1), PAGE[font][0])
    p = ptx.scan(t)[0]
    return t[p['po']:p['po'] + 64]


def _ramp(pal):
    """Grey value -> nearest palette index among the greys (not the key colour)."""
    g = np.frombuffer(pal, np.uint8).reshape(16, 4)
    greys = [i for i in range(16) if g[i, 0] == g[i, 1] == g[i, 2]]
    lut = np.zeros(256, np.uint8)
    for v in range(256):
        lut[v] = min(greys, key=lambda i: abs(int(g[i, 0]) - v))
    return lut


def render(font, pal):
    """-> (index sheet H x W uint8, widths [(draw w, advance)] for 0x20-0x7F)."""
    s = STYLE[font]
    cw, ch = s['cw'], s['ch']
    # size so that 'H' has the wanted cap height
    size = 8
    while True:
        f = ImageFont.truetype(str(FONT), size + 1)
        bb = f.getbbox('H')
        if bb[3] - bb[1] > s['cap']: break
        size += 1
    f = ImageFont.truetype(str(FONT), size)
    htop = f.getbbox('H')[1]
    lut = _ramp(pal)
    rows = -(-96 // COLS)
    sheet = np.full((rows * ch, COLS * cw), s['key'], np.uint8)
    widths = []
    for i in range(96):
        c = chr(0x20 + i)
        big = Image.new('L', (cw * 3, ch * 2), 0)
        ImageDraw.Draw(big).text((cw, s['top'] - htop + 1), c, font=f, fill=255)
        if s['shear']:
            # lean right: shift each row by shear * (baseline - y)
            base = s['top'] + s['cap']
            big = big.transform(big.size, Image.AFFINE, (1, s['shear'], -s['shear'] * base, 0, 1, 0), Image.BILINEAR)
        a = np.asarray(big, np.float32) / 255
        a = a[1:ch + 1]                               # rows of the cell (rendered one row down for the outline)
        cov = a > 0.25
        if c == ' ' or not cov.any():
            widths.append((1, max(3, round(f.getlength(' ') * 0.8))))
            continue
        xs = np.nonzero(cov.any(0))[0]
        x0, x1 = xs[0], xs[-1] + 1
        g = np.zeros((ch, x1 - x0 + 2), np.float32)
        g[:, 1:-1] = a[:, x0:x1]
        m = g > 0.25
        edge = np.zeros_like(m)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                edge |= np.roll(np.roll(m, dy, 0), dx, 1)
        out = np.full(g.shape, s['key'], np.uint8)
        out[edge] = s['edge']
        out[m] = lut[np.clip(g[m] * 255, 0, 255).astype(np.uint8)]
        out[m & (g > 0.85)] = s['fill']
        w = min(out.shape[1], cw)
        gx, gy = (i % COLS) * cw, (i // COLS) * ch
        sheet[gy:gy + ch, gx:gx + w] = out[:, :w]
        widths.append((w, w - 1))                     # outlines of neighbours overlap by one pixel
    return sheet, widths


def ptx_loaded(e, idx, pal):
    """Add a linear CLUT4 PTX in its loaded form (byte 3 = 1, palette and pixel offsets made absolute) to the blob."""
    # the loader zeroes the alpha of magenta palette entries (seen in RAM on every loaded PTX); do the same
    pal = b''.join(c[:3] + b'\0' if c[:3] == b'\xff\x00\xff' else c for c in (pal[i:i + 4] for i in range(0, 64, 4)))
    h, w = idx.shape
    lw = max(3, (w - 1).bit_length())
    lh = max(3, (h - 1).bit_length())
    stride = 1 << lw
    px = np.zeros((h, stride), np.uint8)
    px[:, :w] = idx
    data = (px[:, 0::2] | (px[:, 1::2] << 4)).astype(np.uint8).tobytes()
    v = e.add(bytes(0x60) + data, 16)
    hdr = struct.pack('<4sBBHHHBBBBI4BII', b'PTX\x01', lw, lh, stride, w, h, 4, 0, 3, 2, 16,
                      15 - lw, 15 - lh, 0x11, 0, v + 0x20, v + 0x60)
    e.blob[v - e.base:v - e.base + 0x20] = hdr
    e.blob[v - e.base + 0x20:v - e.base + 0x60] = pal
    e.reloc(v + 0x18, 'R_MIPS_32')
    e.reloc(v + 0x1C, 'R_MIPS_32')
    return v


WRAP = """
wrap:
  addiu $t0, $a1, -1
  sltiu $t0, $t0, 4
  bnez $t0, w_vwf
  nop
  j 0xa20e4
  nop
w_vwf:
  addiu $sp, $sp, -16
  sw $ra, 0($sp)
  sw $a0, 4($sp)
  sw $a3, 8($sp)
  andi $t0, $a2, 0x8000
  bnez $t0, w_asc
  nop
  jal 0xa20e4
  nop
  lw $a0, 4($sp)
  lw $a3, 8($sp)
  lh $t1, 4($a3)
  lh $t2, 8($a0)
  b w_place
  addu $t1, $t1, $t2
w_asc:
  bal getdata
  nop
  addiu $t0, $a1, -1
  sll $t0, $t0, 4
  addu $t0, $v0, $t0
  lw $t3, 0($t0)
  lw $t4, 4($t0)
  lhu $t5, 8($t0)
  lhu $t6, 10($t0)
  andi $t7, $a2, 0xff
  addiu $t7, $t7, -0x20
  sll $t8, $t7, 1
  addu $t4, $t4, $t8
  lbu $t1, 1($t4)
  lbu $t8, 0($t4)
  sh $t8, 4($a3)
  sh $t8, 0x10($a3)
  sh $t6, 0x12($a3)
  sw $t3, 0x14($a3)
  andi $t8, $t7, 15
  mult $t8, $t5
  mflo $t8
  sh $t8, 0xc($a3)
  srl $t8, $t7, 4
  mult $t8, $t6
  mflo $t8
  sh $t8, 0xe($a3)
w_place:
  lh $t4, 0($a3)
  blez $t4, w_set
  move $t5, $zero
  lhu $t6, -6($a3)
  andi $t7, $t6, 0x8000
  beqz $t7, w_grid
  nop
  lw $t7, -0x10($a3)
  beqz $t7, w_grid
  nop
  lh $t5, -0x24($a3)
  srl $t6, $t6, 8
  andi $t6, $t6, 0x3f
  b w_set
  addu $t5, $t5, $t6
w_grid:
  lh $t6, 0x1c($a0)
  lh $t7, 8($a0)
  addu $t6, $t6, $t7
  mult $t4, $t6
  mflo $t5
w_set:
  sh $t5, 0($a3)
  lhu $t6, 0x1e($a3)
  andi $t6, $t6, 0xfe
  andi $t1, $t1, 0x3f
  sll $t1, $t1, 8
  or $t6, $t6, $t1
  ori $t6, $t6, 0x8000
  sh $t6, 0x1e($a3)
  lw $ra, 0($sp)
  jr $ra
  addiu $sp, $sp, 16
asc:
  addiu $t0, $a1, -1
  sltiu $t0, $t0, 4
  beqz $t0, asc_jp
  nop
  jr $ra
  ori $v0, $a2, 0x8000
asc_jp:
  j 0xa1fb8
  nop
bstub:
  lh $a2, 4($s0)
  lh $t0, 6($s0)
  lhu $t1, 0x1e($s0)
  andi $t1, $t1, 0x8000
  beqz $t1, b_grid
  addu $a2, $a2, $a3
  ori $t1, $zero, 1
  jr $ra
  mult $a0, $t1
b_grid:
  jr $ra
  mult $a0, $a2
chain:
  lhu $t0, 0x1e($s0)
  andi $t1, $t0, 0x8000
  beqz $t1, ch_done
  nop
  blez $s4, ch_done
  nop
  lhu $t2, -6($s0)
  andi $t3, $t2, 0x8001
  ori $t4, $zero, 0x8001
  bne $t3, $t4, ch_done
  nop
  lw $t3, -0x10($s0)
  beqz $t3, ch_done
  nop
  lw $t3, -0x1c($s0)
  lui $t4, 0xff00
  and $t3, $t3, $t4
  beqz $t3, ch_done
  nop
  lh $t3, -0x24($s0)
  srl $t5, $t2, 8
  andi $t5, $t5, 0x3f
  addu $t3, $t3, $t5
  sh $t3, 0($s0)
  andi $t1, $t0, 1
  beqz $t1, ch_y
  nop
  andi $t1, $t0, 0x4000
  beqz $t1, ch_done
  nop
ch_y:
  lh $t3, -0x22($s0)
  sh $t3, 2($s0)
  ori $t0, $t0, 0x4001
  sh $t0, 0x1e($s0)
ch_done:
  lh $a0, 0($s0)
  jr $ra
  move $a1, $t0
cols3:
  sll $t0, $s2, 1
  addu $s2, $s2, $t0
  jr $ra
  mult $s2, $s1
"""


def patch(e):
    """Apply the VWF to an eboot.Eboot. Returns the blob vaddrs of the routines, for tests and notes."""
    import eboot
    recs, sheets = [], {}
    for font in (1, 2, 3, 4):
        pal = palette(font)
        idx, widths = render(font, pal)
        sheets[font] = (idx, widths)
        tex = ptx_loaded(e, idx, pal)
        wt = e.add(bytes(x for p in widths for x in p))
        recs.append((tex, wt, STYLE[font]['cw'], STYLE[font]['ch']))
    data = e.add(b''.join(struct.pack('<IIHHI', *r, 0) for r in recs), 16)
    for i in range(4):
        e.reloc(data + 16 * i, 'R_MIPS_32')
        e.reloc(data + 16 * i + 4, 'R_MIPS_32')
    # getdata comes first in the code, so its bal return address is known: code + 12
    e.align(4)
    c = e.here()
    off = (data - (c + 12)) & 0xFFFFFFFF
    getdata = (f'getdata:\n  move $t9, $ra\n  bal gd_l\n  nop\ngd_l:\n  lui $v0, {off >> 16:#x}\n'
               f'  ori $v0, $v0, {off & 0xFFFF:#x}\n  addu $v0, $ra, $v0\n  jr $t9\n  move $ra, $t9\n')
    src = getdata + WRAP
    assert e.code(src) == c
    names = _labels(src, c)
    # writer: skip the ligature checks; ASCII in fonts 1-4 -> 0x8000 | c; setter calls through wrap
    e.put(0xA2648, struct.pack('<I', 0x10000000 | ((0xA26D4 - 0xA264C) >> 2)), expect='0c00c714', by='vwf: no ligatures')
    e.jal(0xA26FC, names['asc'], expect='ee87020c', by='vwf: ascii glyphs')
    for site in (0xA2764, 0xA2828, 0xA2844):
        e.jal(site, names['wrap'], expect='3988020c', by='vwf: setter wrapper')
    e.put(0xA25B0, eboot.asm('addiu $a1, $zero, 0xfe', 0xA25B0), expect='feff0524', by='vwf: flag reset')
    # sprite builder: x from +0 when flagged
    e.jal(0xA31A4, names['bstub'], expect='04000686', by='vwf: builder x')
    for a, exp in ((0xA31AC, '06000886'), (0xA31B0, '2130c700'), (0xA31B4, '18008600')):
        e.put(a, bytes(4), expect=exp, by='vwf: builder x')
    # sprite builder: a VWF cell after an absolutely placed VWF cell follows it (menus that place 10 cells a row)
    e.jal(0xA3188, names['chain'], expect='1e000596', by='vwf: chain after absolute cells')
    # title OPTION rows: the menu places and fades in only 10 cells a row (loop at 0x12EBC0); cells 10+ follow by
    # chain and show at once. Widening that loop to 30 hid cells 10+ (0xA4370 per column?): left as is.
    # setSize: 3x columns
    e.jal(0xA3C94, names['cols3'], expect='18005102', by='vwf: setSize 3x cols')
    # dialogue window (0x10BE88, story and tutorial talk): 4 rows at a 16 px pitch instead of 3 at 22, same box
    # height (64 px, was 66); font 1's English glyphs fit in 16 px rows
    e.put(0x10BEAC, eboot.asm('ori $a3, $zero, 4', 0x10BEAC), expect='03000734', by='dialogue: 4 rows')
    e.put(0x10BEC0, eboot.asm('addiu $t3, $zero, -4', 0x10BEC0), expect='02000b34', by='dialogue: row pitch 16')
    e.put(0x10BEE4, eboot.asm('ori $a2, $zero, 4', 0x10BEE4), expect='03000634', by='dialogue: 4 rows')
    return names, sheets


def _labels(src, base):
    """Label -> vaddr for SRC assembled at BASE (one instruction per non-label line)."""
    out, pc = {}, base
    for ln in src.splitlines():
        ln = ln.strip()
        if not ln: continue
        if ln.endswith(':'): out[ln[:-1]] = pc
        else: pc += 4
    return out


_widths = {}


def advances(font):
    """[advance px] for 0x20-0x7F in engine font 1-4 (what the engine adds per character)."""
    if font not in _widths:
        _widths[font] = [a for _, a in render(font, palette(font))[1]]
    return _widths[font]


def line_px(s, font=1):
    """Pixel width of one line of ASCII as the engine lays it out (start of the first glyph to the end of the last).
    Font 0 has no VWF: a fixed 8 px cell per character (before any window spacing)."""
    if font == 0: return len(s) * 8
    adv = advances(font)
    return sum(adv[ord(c) - 0x20] for c in s if 0x20 <= ord(c) < 0x80) + (1 if s else 0)


def preview(path):
    """Each font's sheet and a sample line laid out with its advances, 4x."""
    sample = 'The quick brown fox jumps over the lazy dog. "Hi!" (Lv 99) 1,234G?'
    parts = []
    for font in (1, 2, 3, 4):
        pal = palette(font)
        idx, widths = render(font, pal)
        s = STYLE[font]
        rgba = np.frombuffer(pal, np.uint8).reshape(16, 4).copy()
        rgba[s['key']] = (40, 60, 120, 255)
        line = np.full((s['ch'], 1000), s['key'], np.uint8)
        x = 0
        for c in sample:
            i = ord(c) - 0x20
            w, adv = widths[i]
            gx, gy = (i % COLS) * s['cw'], (i // COLS) * s['ch']
            g = idx[gy:gy + s['ch'], gx:gx + w]
            reg = line[:, x:x + w]
            reg[g != s['key']] = g[g != s['key']]
            x += adv
        parts += [rgba[idx], rgba[line]]
    W = max(p.shape[1] for p in parts)
    im = np.zeros((sum(p.shape[0] + 4 for p in parts), W, 4), np.uint8)
    y = 0
    for p in parts:
        im[y:y + p.shape[0], :p.shape[1]] = p
        y += p.shape[0] + 4
    Image.fromarray(im).resize((W * 3, im.shape[0] * 3), Image.NEAREST).save(path)


if __name__ == '__main__':
    if sys.argv[1:2] == ['preview']:
        preview(sys.argv[2])
