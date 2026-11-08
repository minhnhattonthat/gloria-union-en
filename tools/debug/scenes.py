"""Scene list: name -> (kind, argument, proof). Reached and proved by tools/debug/warp.py.

Kinds: boot (no input), newgame (GAME START), stage (warp to a stage number), mode (force a mode as the title exits),
title (title menu; KEYS picks the row), select (stage's Character Select), ready (stage's Ready screen), field (first player
turn of a stage), fight (stage 1's first Union), enemy (end turns until an enemy-phase fight), outcome (field, then flag
0xA = argument: docs/re/engine.md), skill (enemy, then fire a skill), cleared (title with the clear flag set), extra (EXTRA,
everything unlocked), banner (stage 3's opening with its first event banner swapped for banner ARG: proof.png 50 frames
after it shows, end.png on Tactics Card select with the team banner).
KEYS[name] are buttons pressed once there, 'wait N' to wait.
proof: ('file', id) the game opened that CPK id, ('mode', n) the top-level mode is n, ('stage', n, script) save+0x1A0 is n
and the script opened, ('byte', addr, v) RAM byte, or ('fired',) the skill fired.
"""
import struct

ELF = 'work/re/eboot.elf'
STAGE_TABLE = 0x2C7544    # 91 records of 0x1C bytes, docs/re/engine.md
STAGE_COUNT = 91
FIELD_STAGE = 3           # 1_02_AP: no tutorial and a short story, so the field is about a minute from boot
UNION_STAGE = 1           # 1_01_AP: the only stage with a known route to an enemy
MENU_ROWS = ['full_map', 'unit_list', 'card_list', 'weapon_list', 'terrain_list', 'object_list', 'tutorial', 'win_conditions', 'suspend']
TITLE_ROWS = ['load_data', 'continue', 'option', 'data_install']


def stages():
    """-> [(number, name, title file, script file)] from the EBOOT."""
    d = open(ELF, 'rb').read()
    out = []
    for n in range(STAGE_COUNT):
        title, _, script, _, nm = struct.unpack_from('<IIHHI', d, STAGE_TABLE + n * 0x1C + 0xA0)
        out.append((n, d[nm + 0xA0:d.index(b'\0', nm + 0xA0)].decode(), title, script))
    return out


EXTRA = 0x8B88EA8         # RAM: EXTRA work, +0x9B is the open page, row + 1 (table at rodata 0x289680)
EXTRA_PAGES = ['scenario', 'character', 'card', 'item', 'music', 'audio_drama']

KEYS = {'card_select': ('down', 'circle'), 'card_data': ('down', 'circle', 'wait 120', 'down', 'right', 'triangle'),
        'card_victory': ('down', 'circle', 'wait 120', 'ltrigger'), 'char_status': ('triangle',), 'equip_tab': ('left',),
        'item_tab': ('right',), 'char_caution': ('cross',), 'pre_map': ('rtrigger',), 'unit_status': ('rtrigger', 'cross', 'triangle'),
        'map_menu': ('ltrigger',), 'turn_end_ok': ('ltrigger', 'circle'), 'tactic_card': ('ltrigger', 'circle', 'circle'),
        'fight': ('circle',), 'skill_gauge': ('wait 600', *['circle'] * 12)}
for i, r in enumerate(MENU_ROWS, 1): KEYS[f'menu_{r}'] = ('ltrigger', *['down'] * i, 'circle')
for i, r in enumerate(TITLE_ROWS, 1): KEYS[f'title_{r}'] = (*['down'] * i, 'circle')
for i, r in enumerate(EXTRA_PAGES): KEYS[f'extra_{r}'] = (*['down'] * i, 'wait 30', 'circle')
KEYS['battle_setting'] = ('circle',)
KEYS['menu_tutorial'] = ('tutorials', *KEYS['menu_tutorial'])
KEYS['tutorial_play'] = (*KEYS['menu_tutorial'], 'wait 60', 'circle', 'wait 240', 'circle', 'wait 120')
KEYS['game_over_title'] = ('wait 900', 'down', 'circle', 'wait 300')


def scenes():
    s = {'title': ('boot', None, ('mode', 2)),
         'prologue': ('newgame', None, ('file', 2022)),
         'credits': ('mode', 39, ('file', 1992))}
    st = stages()
    for n, name, title, script in st:
        s[f'stage_{name}'] = ('stage', n, ('stage', n, script))
    # chapter cards play when a chapter's first stage loads: cards are 1582 + chapter - 1
    first = {}
    for n, name, *_ in st: first.setdefault(int(name[0]), n)
    for c, n in first.items():
        s[f'card_ch{c}'] = ('stage', n, ('file', 1581 + c))
    s['scenario_select'] = ('stage', first[3], ('file', 2427))
    s['tutorial'] = ('stage', first[3], ('file', 2023))
    s['ending_letters'] = ('stage', 90, ('file', 1651))
    for name, proof in [('character_select', ('mode', 20)), ('card_select', ('mode', 26)), ('card_data', ('mode', 28)),
                        ('card_victory', ('mode', 18)), ('char_status', ('mode', 29)), ('equip_tab', ('mode', 21)),
                        ('item_tab', ('mode', 22)), ('char_caution', ('mode', 20)), ('pre_map', ('mode', 16))]:
        s[name] = ('select', 1, proof)
    s['ready'] = ('ready', 1, ('mode', 27))
    for name, proof in [('field', ('mode', 15)), ('unit_status', ('mode', 29)), ('map_menu', ('mode', 16)),
                        ('turn_end_ok', ('mode', 16)), ('tactic_card', ('mode', 32)), ('menu_full_map', ('mode', 16)),
                        ('menu_unit_list', ('file', 1757)), ('menu_card_list', ('file', 2426)), ('menu_weapon_list', ('mode', 16)),
                        ('menu_terrain_list', ('mode', 16)), ('menu_object_list', ('file', 1703)), ('menu_tutorial', ('mode', 16)),
                        ('menu_win_conditions', ('mode', 18)), ('menu_suspend', ('file', 2020))]:
        s[name] = ('field', FIELD_STAGE, proof)
    s['tutorial_play'] = ('field', FIELD_STAGE, ('file', 2023))
    for n in range(47):   # event banners, files 1945-1991 (op 0x4A); warp.py swaps the stage's first banner for n
        s[f'banner{n:02d}'] = ('banner', n, ('file', 1945 + n))
    s['union'] = ('fight', UNION_STAGE, ('mode', 33))
    s['fight'] = ('fight', UNION_STAGE, ('mode', 34))
    s['battle_result'] = ('fight', UNION_STAGE, ('mode', 35))
    s['skill_gauge'] = ('enemy', FIELD_STAGE, ('mode', 34))
    s['game_over'] = ('outcome', 2, ('file', 1758))
    s['game_over_title'] = ('outcome', 2, ('mode', 2))
    s['stage_clear'] = ('outcome', 4, ('file', 1704))
    for r in TITLE_ROWS: s[f'title_{r}'] = ('title', None, ('mode', 2))
    s['skill_cutin'] = ('skill', FIELD_STAGE, ('fired',))
    s['battle_setting'] = ('cleared', None, ('mode', 2))
    s['extra_menu'] = ('extra', None, ('file', 2430))
    for row, name in enumerate(EXTRA_PAGES):
        s[f'extra_{name}'] = ('extra', None, ('byte', EXTRA + 0x9B, row + 1))
    return s
