"""Insertion (tools/insert.py) and the VWF patch (tools/vwf.py), on the marker and English builds, without an emulator."""
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import insert  # noqa: E402
import vm  # noqa: E402
import vwf  # noqa: E402
from extract import ELF, FILES, SUBS, fct, from_text  # noqa: E402

pytestmark = pytest.mark.skipif(not ELF.exists(), reason='no work/re/eboot.elf')


@pytest.fixture(scope='module', params=['marker', 'en'])
def built(request):
    ins = insert.Inserter(request.param)
    return ins, ins.eboot(), ins.cpk()


def cstr(b, p):
    return bytes(b[p:b.index(0, p)])


def want(ins, x):
    """The bytes a slot must read: the build's text, or the original when the build keeps it (None)."""
    t = ins.text(x)
    return from_text(x['jp'] if t is None else t)


def test_scripts_point_at_text(built):
    """Every slot of every changed script reads its own text (tag kept); code bytes outside text spans unchanged."""
    ins, _, files = built
    sec = fct(files[SUBS[0]], SUBS[1])
    n = 0
    for sub, entries in [('story/' + p.stem, json.loads(p.read_text('utf8'))) for p in (ROOT / 'script/story').glob('*.json')] + \
                        [('common/' + p.stem, json.loads(p.read_text('utf8'))) for p in (ROOT / 'script/common').glob('*.json')]:
        if sub.startswith('story'):
            i = int(sub[6:]); old = (FILES / f'{i:05d}.bin').read_bytes(); new = files[i]
        else:
            k = int(sub[10:]); old = fct(fct((FILES / '00003.bin').read_bytes(), SUBS[1]), k); new = fct(sec, k)
        spans = vm.parse(old) if sub.startswith('story') else insert.vm.parse(old, *((0x10, struct.unpack_from('<I', old, 0)[0]) if k == 7 else (struct.unpack_from('<I', old, 0)[0], len(old)))) if k not in (5, 6) else []
        text = {(s.off, s.end) for s in spans if s.kind == 'text'}
        slots = {int(s, 16) for x in entries for s in x.get('slots', [])}
        inplace = {q for x in entries if 'at' in x for q in range(int(x['at'], 16), int(x['at'], 16) + x['max'])}
        for s in spans:
            if s.kind == 'op':
                for q in range(s.off, s.end):
                    if q not in inplace and not any(a <= q < a + 4 for a in slots):
                        assert new[q] == old[q], (sub, hex(q))
        for x in entries:
            if 'at' in x:
                at, mx = int(x['at'], 16), x['max']
                # op 0x74 skips strlen bytes, so the in-place string keeps its exact length (space padded)
                assert cstr(new, at) == want(ins, x)[:mx].ljust(mx, b' '), x['id']
                continue
            for s in x['slots']:
                p = struct.unpack_from('<I', new, int(s, 16))[0]
                if 'voice' in x:
                    assert new[p:p + 2] == b'\x02\x00' and struct.unpack_from('<H', new, p + 2)[0] == x['voice']
                    p += 4
                assert cstr(new, p) == want(ins, x), (x['id'], s)
                n += 1
    assert n > 9000


def test_eboot_points_at_text(built):
    ins, out, _ = built
    e = ins.eb
    descs = insert.item_descs(e)
    mem = bytes(e.d[:e.ph[0][4] + 0xA0])   # segment 0 as patched; blob separately
    blob = bytes(e.blob)

    def read(v):
        if v >= e.base: return cstr(blob, v - e.base)
        return cstr(mem, v + 0xA0)
    n = 0
    for p in (ROOT / 'script/eboot').glob('*.json'):
        for x in json.loads(p.read_text('utf8')):
            if x['status'] == 'data': continue   # untouched; some are pointer tables that decode, and their words move
            t = ins.text(x)   # the text, a compact marker, or None (original kept)
            if t is not None and x['id'] in descs: t = t.replace('\n', ' ')   # one row; breaks in a table
            w = from_text(x['jp'] if t is None else t)
            for s in x['slots']:
                k, *a = s.split(':')
                a = [int(y, 16) for y in a]
                if k == 'w':
                    v = e.word(a[0])
                else:
                    v = ((e.word(a[0]) & 0xFFFF) << 16) + struct.unpack('<h', struct.pack('<H', e.word(a[1]) & 0xFFFF))[0]
                assert read(v) == w, (x['id'], s)
                n += 1
    assert n > 10000


def test_eboot_writes(built):
    """romdiff over EBOOT segment 0 with the build's write log: every changed byte has a logged write, each write
    found the original bytes it expected, none overlaps or was overwritten later (new code and strings go to the blob
    in segment 1, outside this range)."""
    import romdiff
    e = built[0].eb
    end = e.ph[0][4] + 0xA0
    writes = [(int(o, 16), bytes.fromhex(a), bytes.fromhex(b), by) for o, a, b, *rest in
              (ln.split(None, 3) for ln in e.log) for by in [rest[0] if rest else '']]
    assert len(writes) > 1000 and all(o + len(a) <= end for o, a, _, _ in writes)
    errs, ok = romdiff.check(e.orig[:end], bytes(e.d[:end]), set(), writes)
    assert not errs, errs[:10]
    assert ok > 0


def test_format_buffers():
    """No inserted format string outputs more bytes than its sprintf buffer holds (tbl/fmtbuf.tsv; the battle_result
    crash: '%2d戦%2d勝' marker overflowed a 16-byte stack buffer)."""
    ins = insert.Inserter('marker')
    lim = insert.buf_limits()
    assert len(lim) >= 9
    for p in (ROOT / 'script/eboot').glob('*.json'):
        for x in json.loads(p.read_text('utf8')):
            t = ins.text(x)
            if x['id'] in lim and t is not None: assert insert.fmt_bytes(t) <= lim[x['id']], x['id']
    with pytest.raises(ValueError):
        insert.Inserter('marker', qa={'e:1edc5c': '%2d wins and %2d losses'}).text({'id': 'e:1edc5c', 'jp': '%2d戦%2d勝', 'en': '', 'status': 'todo'})
    # EXTRA list titles go through "%02d %s" into 32 bytes: 28 left for the title
    assert lim['e:289288'] == 28 and lim['e:284cd0'] == 28


def test_win_condition_icon_cells():
    """Win conditions put a flag sprite in place of the cell at the (row, col) where JP has ■ (seen in game: stage
    2-03 B), so the English ■ must sit at the same line and character index. Masked item names use ■ as a glyph."""
    def cells(t): return [(r, c) for r, line in enumerate(t.split('\n')) for c, ch in enumerate(line) if ch == '■' and c]
    for s in json.load(open(ROOT / 'script/eboot/ui3.json', encoding='utf8')):
        if s.get('en') and cells(s['jp']): assert cells(s['en']) == cells(s['jp']), s['id']


def test_item_desc_breaks():
    """Item descriptions: break cells are the index of each later line's first character, every line fits, too many
    lines fail an English build."""
    t = 'A sturdy steel helmet. It guards the head well.'
    b = insert.desc_breaks(t, 134, 2, 3, 2)
    assert 0 < b[0] < b[1] < len(t) and t[b[0] - 1] == ' ' and t[b[1] - 1] == ' '
    for s in (t[:b[0]], t[b[0]:b[1]], t[b[1]:]): assert vwf.line_px(s.strip(), 2) <= 134
    assert insert.desc_breaks('Short.', 134, 2, 3, 2) == [0, 0]
    with pytest.raises(ValueError): insert.desc_breaks('word ' * 40, 134, 2, 3, 2)


def test_vwf_widths():
    """Every printable glyph fits its cell and advances; space is narrow; a wide letter is wider than a narrow one."""
    for font in (1, 2, 3):
        idx, w = vwf.render(font, vwf.palette(font))
        assert len(w) == 96 and all(1 <= d <= vwf.STYLE[font]['cw'] and a >= 2 for d, a in w), font
        adv = vwf.advances(font)
        assert adv[ord('M') - 32] > adv[ord('i') - 32] and adv[0] < adv[ord('n') - 32]
    assert 260 < vwf.line_px('The quick brown fox jumps over the lazy dog.', 1) < 330   # about 6.6 px a character
    # font 1 ink fits the dialogue's 16 px row pitch (4 rows in the box)
    idx, _ = vwf.render(1, vwf.palette(1))
    ink = (idx != vwf.STYLE[1]['key']).reshape(6, 20, -1).any(2).any(0).nonzero()[0]
    assert ink.max() - ink.min() + 1 <= 16


def test_asm_one_instruction_per_line():
    """keystone must not expand a label jal into a $gp call (it did, depending on earlier calls)."""
    import eboot
    e = eboot.Eboot(ELF.read_bytes())
    names, _ = vwf.patch(e)
    for _ in range(3):
        eboot.asm('jal 0x3b3d00', 0xA2764)
        assert len(eboot.asm('x:\n  bal x\n  nop', 0x3B0000)) == 8
