"""Scene list: name -> (kind, argument, proof). Reached and proved by tools/debug/warp.py.

Kinds: boot (no input), newgame (GAME START), stage (warp to a stage number), mode (force a mode as the title exits).
proof: ('file', id) the game opened that CPK id, or ('mode', n) the top-level mode reached n.
"""
import struct

ELF = 'work/re/eboot.elf'
STAGE_TABLE = 0x2C7544    # 91 records of 0x1C bytes, docs/re/engine.md
STAGE_COUNT = 91


# after reaching mode 20, buttons that lead on to the scene's proof (mashing Circle stays on the Must Entry unit)
AFTER_CHAR_SELECT = {'card_select': ('down', 'circle')}


def stages():
    """-> [(number, name, title file, script file)] from the EBOOT."""
    d = open(ELF, 'rb').read()
    out = []
    for n in range(STAGE_COUNT):
        title, _, script, _, nm = struct.unpack_from('<IIHHI', d, STAGE_TABLE + n * 0x1C + 0xA0)
        out.append((n, d[nm + 0xA0:d.index(b'\0', nm + 0xA0)].decode(), title, script))
    return out


def scenes():
    s = {'title': ('boot', None, ('mode', 2)),
         'prologue': ('newgame', None, ('file', 2022)),
         'credits': ('mode', 39, ('file', 1992))}
    st = stages()
    for n, name, title, script in st:
        s[f'stage_{name}'] = ('stage', n, ('file', script))
    # chapter cards play when a chapter's first stage loads: cards are 1582 + chapter - 1
    first = {}
    for n, name, *_ in st: first.setdefault(int(name[0]), n)
    for c, n in first.items():
        s[f'card_ch{c}'] = ('stage', n, ('file', 1581 + c))
    s['scenario_select'] = ('stage', first[3], ('file', 2427))
    s['tutorial'] = ('stage', first[3], ('file', 2023))
    s['character_select'] = ('stage', 1, ('mode', 20))
    s['card_select'] = ('stage', 1, ('mode', 26))
    s['ending_letters'] = ('stage', 90, ('file', 1651))
    return s
