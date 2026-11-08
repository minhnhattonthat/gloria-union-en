"""Insert text from script/ into the EBOOT, the story scripts and the common subs.

    from insert import Inserter
    ins = Inserter(mode)            # 'en': English where an entry has it, else the original; 'marker': every line marked
    ebytes = ins.eboot()            # patched EBOOT (VWF + strings)
    files = ins.cpk()               # {CPK id: bytes} for the story scripts and id 3

Where text goes (docs/re/text.md):
- EBOOT: a string that fits its old bytes stays in place, else it moves to the blob; `w:` words and `i:` lui/lo pairs
  are rewritten. Relocations already cover them (blob vaddrs use the same address base as segment 0).
- Story scripts and common subs: each text (voice tag + body + NUL) is placed first-fit into the freed old text spans,
  else appended after the end of the file; the u32 slots get the new offset. Code never moves.
- Team names (op 0x74) and the bare subs 5 and 6 have no pointer: written in place, cut to `max` bytes.
"""
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import eboot as eb  # noqa: E402
import vm  # noqa: E402
import vwf  # noqa: E402
from extract import ELF, FILES, SUBS, fct, from_text  # noqa: E402

SCRIPT = ROOT / 'script'
FMT = re.compile(r'%[-+ 0#]*\d*(?:\.\d+)?[hlL]?[diouxXcsfeEgGp%]')
FILLER = 'The quick brown fox jumps over the lazy dog and keeps on running far away'


def load(sub):
    out = {}
    for p in sorted((SCRIPT / sub).glob('*.json')):
        out[p.stem] = json.loads(p.read_text('utf8'))
    return out


def fmt_bytes(text):
    """Widest output, in bytes, of a printf string: each code at its widest (%d 3 digits or its width, %s 0), the
    rest as encoded."""
    def w(code):
        if code == '%%': return 1
        n = int(re.match(r'%[-+ 0#]*(\d*)', code).group(1) or 0)
        if code[-1] in 'di': return max(n, 3)   # shortcut: counts here are <= 999; a bigger value needs more
        return 0 if code[-1] == 's' else max(n, 1)
    return sum(w(c) for c in FMT.findall(text)) + len(from_text(FMT.sub('', text)))


def buf_limits(_c={}):
    """{entry id: max output bytes} for format strings sprintf'd into stack buffers (tbl/fmtbuf.tsv, tools/fmtbuf.py)."""
    if 'l' not in _c:
        p = ROOT / 'tbl' / 'fmtbuf.tsv'
        rows = [r.split('\t') for r in p.read_text('utf8').splitlines()[1:]] if p.exists() else []
        _c['l'] = {}
        for r in rows:
            m = re.match(r'\d+', r[4])
            if m: _c['l'][r[0]] = min(int(m.group()), _c['l'].get(r[0], 1 << 30))
    return _c['l']


# item descriptions: three screens place row 0's cells by hand and start line 2 at a break cell read from a per-item
# table (docs/re/text.md §Item descriptions). Table of description pointers -> its break table.
DESC_BRK2, DESC_BRK3 = 0x2CA458, 0x2F86F0   # 1 break byte per item (item screens) / 2 per item (EXTRA item page)
DESC_TABLES = {0x2CCAB0: DESC_BRK2, 0x2CCECC: DESC_BRK3}
DESC_ITEMS = 261
# break table -> (px per line, font, lines, break bytes): EXTRA item page (font 2 from x 298, docs/re/text.md);
# item screens 0xE0FE8/0xE11CC (font 1, 13 cells at 18 px from x 24: read from code, no shot yet)
DESC_FIT = {DESC_BRK3: (134, 2, 3, 2), DESC_BRK2: (234, 1, 2, 1)}


def item_descs(e):
    """{entry id: [(break table, item index)]} from the description pointer tables."""
    out = {}
    for ptrs, brk in DESC_TABLES.items():
        for i in range(DESC_ITEMS):
            out.setdefault(f'e:{e.word(ptrs + 4 * i):06x}', []).append((brk, i))
    return out


def desc_breaks(t, px, font, lines, nbytes, strict=True):
    """Break cells for an item description wrapped by words to PX of FONT: the index of each later line's first
    character (a space ending a line stays on it as an invisible cell), 0 = no more breaks. strict: more than LINES
    lines raises (an English build); a marker runs on in its last line."""
    out, start, cur = [], 0, ''
    for w in t.split(' '):
        if cur and vwf.line_px(cur + ' ' + w, font) > px:
            start += len(cur) + 1; out.append(start); cur = w
        else:
            cur = cur + ' ' + w if cur else w
    if strict and (len(out) >= lines or vwf.line_px(cur, font) > px):
        raise ValueError(f'item description over {lines} lines of {px} px (font {font}): {t!r}')
    assert not re.search(r'\[[0-9A-Fa-f]{2}\]', t), 'codes in an item description: break cells count characters'
    return (out[:lines - 1] + [0] * nbytes)[:nbytes]


def short(eid):
    """Marker id: story s2032:00028 -> 2032:28, common c7:001a0 -> c7:1a0, EBOOT e:1ed94c -> 1ed94c."""
    k, _, off = eid.partition(':')
    off = off.lstrip('0') or '0'
    return off if k == 'e' else f'{k.lstrip("s")}:{off}'


def marker(e, width=None):
    """[id] + filler, keeping the line count, printf codes and real newlines of the original."""
    jp = e['jp']
    codes = ' '.join(FMT.findall(jp))
    lines = jp.split('\n')
    out = []
    for i, ln in enumerate(lines):
        n = width or max(8, len(ln.encode('cp932')) + 4)
        head = f'[{short(e["id"])}]' if i == 0 else f'{i + 1}'
        s = (head + ' ' + FILLER)[:n] if n > len(head) else head
        if i == len(lines) - 1 and codes:
            s += ' ' + codes
        out.append(s)
    t = '\n'.join(out)
    if '[0A]' in jp:   # keep EBOOT hard newlines in the same count
        t = t + '[0A]' * jp.count('[0A]') if '[0A]' not in t else t
    return t


class Inserter:
    def __init__(self, mode='en', only=None, qa=None):
        assert mode in ('en', 'marker')
        self.mode, self.only, self.qa = mode, only, qa or {}

    def text(self, e):
        """New text for an entry, or None to leave it as it is. A format string that would overflow its sprintf
        buffer fails the build; a marker that would is left out (the original stays)."""
        t = self._text(e)
        lim = buf_limits().get(e['id'])
        if t is not None and lim is not None and fmt_bytes(t) > lim:
            if self.mode == 'marker' and e['id'] not in self.qa:   # marker mode ignores the English
                t = f'[{short(e["id"])}]' + ''.join(FMT.findall(e['jp']))   # compact marker: id and codes
                return t if fmt_bytes(t) <= lim else None
            raise ValueError(f'{e["id"]}: {fmt_bytes(t)} bytes of output, buffer holds {lim} (tbl/fmtbuf.tsv): {t!r}')
        return t

    def _text(self, e):
        if e['id'] in self.qa:
            return self.qa[e['id']]
        if e['status'] == 'data':
            return None
        if self.only and not any(e['id'].startswith(p) for p in self.only):
            return None
        if self.mode == 'marker':
            return marker(e)
        return e['en'] or None

    # EBOOT ---------------------------------------------------------------------------------------------------------
    def eboot(self, elf_bytes=None):
        d = elf_bytes or ELF.read_bytes()
        e = eb.Eboot(d)
        vwf.patch(e)
        descs = item_descs(e)
        for entries in load('eboot').values():
            for x in entries:
                t = self.text(x)
                if t is None: continue
                if x['id'] in descs:   # one row of cells, new lines at break cells (vwf.py: item descriptions)
                    t = t.replace('\n', ' ')
                    strict = self.mode == 'en' and x['id'] not in self.qa
                    for table, i in descs[x['id']]:
                        b = bytes(desc_breaks(t, *DESC_FIT[table], strict))
                        e.put(table + i * len(b), b, by=x['id'] + ' breaks')
                raw = from_text(t) + b'\0'
                old = int(x['id'][2:], 16)
                oldlen = len(from_text(x['jp'])) + 1
                if len(raw) <= oldlen:
                    e.put(old, raw.ljust(oldlen, b'\0'), expect=from_text(x['jp']) + b'\0', by=x['id'])
                    continue
                v = e.add(raw, 1)
                for s in x['slots']:
                    kind, *a = s.split(':')
                    a = [int(y, 16) for y in a]
                    if kind == 'w':
                        assert e.word(a[0]) == old, s
                        e.put(a[0], struct.pack('<I', v), by=x['id'])
                    else:
                        self._pair(e, a[0], a[1], old, v, x['id'])
        self.eb = e
        return e.build()

    def _pair(self, e, lui, lo, old, v, by):
        """Point a lui/lo pair at v. A lui shared by several lo's (same string) is rewritten once."""
        luis = self.__dict__.setdefault('luis', {})
        wl, wo = struct.unpack_from('<I', e.orig, lui + 0xA0)[0], struct.unpack_from('<I', e.orig, lo + 0xA0)[0]
        assert wl >> 26 == 0x0F, f'{lui:#x} is not lui ({by})'
        assert wo >> 26 != 0x0D, f'{lo:#x} is ori: unsigned low half ({by})'
        assert ((wl & 0xFFFF) << 16) + struct.unpack('<h', struct.pack('<H', wo & 0xFFFF))[0] == old, by
        hi, lo16 = (v + 0x8000) >> 16, v & 0xFFFF
        if lui in luis:
            assert luis[lui] == (by, hi), f'lui {lui:#x} shared by {luis[lui][0]} and {by}'
        else:
            luis[lui] = (by, hi)
            e.put(lui, struct.pack('<I', (wl & 0xFFFF0000) | hi), by=by)
        e.put(lo, struct.pack('<I', (wo & 0xFFFF0000) | lo16), by=by)

    # scripts ---------------------------------------------------------------------------------------------------------
    def script(self, b, entries):
        """Script bytes with its texts moved. Returns new bytes (old ones if nothing changed)."""
        b = bytearray(b)
        news, free = [], []
        for x in entries:
            t = self.text(x)
            if t is None: continue
            if 'at' in x:   # in place, no pointer
                at, mx = int(x['at'], 16), x['max']
                raw = from_text(t)[:mx]
                assert b[at + mx] == 0 and 0 not in b[at:at + mx], x['id']
                b[at:at + mx] = raw.ljust(mx, b' ')   # the VM skips strlen bytes: the length must not change
                continue
            if not x['slots']:
                continue   # no pointer: nothing reads it
            off = int(x['id'].split(':')[1], 16)
            end = vm.strend(b, off + (4 if 'voice' in x else 0)) + 1
            tag = b[off:off + 4] if 'voice' in x else b''
            assert tag == b'' or tag[:2] == b'\x02\x00'
            free.append([off, end])
            news.append((tag + from_text(t) + b'\0', x['slots']))
        if not news:
            return bytes(b)
        free.sort()
        for f in free:   # wipe the old spans so a leftover can't be read
            b[f[0]:f[1]] = bytes(f[1] - f[0])
        news.sort(key=lambda n: -len(n[0]))
        for raw, slots in news:
            spot = next((f for f in free if f[1] - f[0] >= len(raw)), None)
            if spot:
                at = spot[0]
                spot[0] += len(raw)
            else:
                b += bytes(-len(b) % 4)
                at = len(b)
                b += raw
            b[at:at + len(raw)] = raw
            for s in slots:
                struct.pack_into('<I', b, int(s, 16), at)
        b += bytes(-len(b) % 4)
        return bytes(b)

    def cpk(self):
        out = {}
        for name, entries in load('story').items():
            i = int(name)
            b = (FILES / f'{i:05d}.bin').read_bytes()
            nb = self.script(b, entries)
            if nb != b: out[i] = nb
        top = (FILES / f'{SUBS[0]:05d}.bin').read_bytes()
        sec = fct(top, SUBS[1])
        subs = {}
        for name, entries in load('common').items():
            n = int(name[3:])
            b = fct(sec, n)
            nb = self.script(b, entries)
            if nb != b: subs[n] = nb
        if subs:
            out[SUBS[0]] = fct_pack(top, {SUBS[1]: fct_pack(sec, subs)})
        return out


def fct_pack(b, repl):
    """FCT b with sections in repl replaced: header kept, sections laid out in order at 16-byte alignment."""
    n, h = struct.unpack_from('<II', b, 4)
    tab = [struct.unpack_from('<II', b, h + 8 * i) for i in range(n)]
    out = bytearray(b[:tab[0][0]])
    for i, (o, s) in enumerate(tab):
        d = repl.get(i, b[o:o + s])
        out += bytes(-len(out) % 16)
        struct.pack_into('<II', out, h + 8 * i, len(out), len(d))
        out += d
    out += bytes(-len(out) % 16)
    return bytes(out)
