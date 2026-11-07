# Engine map (phase 2)

Addresses are EBOOT vaddrs (file offset - 0xA0) unless marked RAM. Disassembly for grep: `python -X utf8 tools/mkasm.py` writes `work/re/eboot.asm`.

## Load addresses (verified: mode global reads 2 on the title)

- Segment 0 loads at RAM 0x8804000. Segment 1 (.bss, vaddr 0x300588) loads at RAM 0x8B04588.
- **Code that names .bss uses addresses relative to segment 1, not vaddrs:** `lui $a1, 8; lw 0xc34($a1)` is RAM 0x8B04588 + 0x80C34 = 0x8B851BC. A `lui` of 7 to 0xB is .bss; 0x25 to 0x2F is rodata/.data at base + vaddr. The relocation table decides; the first write to 0x8884C34 was silently into .text.

## Globals

| RAM | vaddr form | What |
|---|---|---|
| 0x8B851BC | seg1 +0x80C34 | **mode**: index into the handler table at 0x2B6650 |
| 0x8ABB5F0 | 0x2B75F0 | pointer to the save/work struct |
| 0x8ABA638 | 0x2B6638 | request flags, cleared each frame: 0x100 continue load, 0x200, 0x400 |
| 0x8ABA640 | 0x2B6640 | next stage number, used when 0x2B6798 bit 0x10000 is set |
| 0x8ABA798 | 0x2B6798 | bit 0x10000: load stage 0x2B6640 at the next dispatch |

Save struct: `+0x1A0` s16 current stage. Story flags: `0x56B4(save, i)` reads, `0x5408(save, i, v)` writes: i < 0x61 at +0x20+i, 0x61-0x7F at +0x81+(i-0x61), 0x80-0x8A at +0xA0+(i-0x80).

## Stages

`loadStage(stage, a1, a2)` at 0xADC7C. Stage table at 0x2C7544, 91 records of 0x1C bytes:

| Off | Type | What |
|---|---|---|
| +0 | u32 | stage title file (1850+) |
| +8 | u16 | script file (2032-2082) |
| +A | u16 | entry point inside the script |
| +C | ptr | name, `1_01_A`, chapter_stage_variant; a `P` suffix is a variant with a Prologue-type replay |
| +10 | u8 | scenario number |
| +11, +12 | u8 | script index; chapter-range byte (< 8 ch1-2, < 0x23, < 0x28, < 0x2F) |
| +14 | ptr | optional extra table |
| +18, +1A | u16 | first option and count in the scenario-select table (0xFFFF: no select) |

Other files follow the stage: byte table at rodata 0x2BEBE0 (copied by loadStage) gives 1759 + n; chapter card 1582 + chapter.

**Scenario select** (0x87564) lists options i in 0..16 whose flag 0x21+i is 1 or 3, from the table at 0x2BC654 (0x1C each). With none set it reads a null entry and crashes. `gu.warp()` sets all 17.

## Modes (handler table 0x2B6650, 48 slots)

Forcing a mode from the title takes effect when the title exits. Seen from the sweep: 1 boot logos, 2 title, 5 chapter card, 7 in-game (0x4000), 38 chapter load, 39 credits (`CAST` page, id 1992), 40 back to title, 41 after credits. 4 is reached from 0x85310 (title); 12 from 17. Most others crash forced from the title: they expect their caller's setup.

Game over: 0x12A188 (loads 1758), called from the mode 7 handler at 0x41F8.

Ending letters: 0x114690 (id 1651), reached through function pointer 0x11DEF4 in the table at 0x2EF9F4 (guess: script op table).

Script ops: 256-entry handler table at 0x2EF748. Op 0xAB (`ab 09 <side> <u16 id> <x> <y>`) is the letter page, used by scripts 2080-2082 and some others. So stages 88-90 play the ending, and the letters come from warping there.

## Battle flow (verified: every step is a scene in `tools/debug/scenes.py`)

Character Select (mode 20): Left equipment (21), Right items (22), Triangle status (29), R stage map (16), Cross on a Must Entry unit is the CAUTION box. Down then Circle: Card Select (26).

Card Select work struct at RAM 0x8B8C218 (seg1 +0x87C90): +1 state, +2 scroll, +3 cursor row, +4 cursor index, +0xC cards needed, +0xD cards taken, +0x5C8 list order, +0x20 + n*0x18 records (byte 0 bit 0: selectable, bit 1: taken). **The battle starts by taking the last card**: when +0xD reaches +0xC the state goes 0x67, 0x68, then Ready (27). The screen says `2/5` and that means taken/needed. Stage 1 has only 6 selectable cards of 41, so most rows do nothing. Triangle: card data (28), L: win conditions (18), R: map (16).

Ready (27, `戦闘準備OK?`), Circle: mode 7 runs the opening script, then the player turn is **mode 15**. Field: L map menu (mode 16; rows in order Turn End, Full Map, Unit List, Card List, Weapon List, Terrain List, Object List, Tutorial, Win Conditions (18), Suspend), R next unit, Cross then Triangle unit status (29), Circle takes a unit, D-pad walks it, Circle puts it down. Square with no unit in hand and an enemy adjacent (`Press □ for Union!`) opens the Union screen (33), Circle: Fight (34), result (35). Turn End goes to the enemy phase (still mode 15; its fights are modes 33-35 and need Circle), then the Tactics Card pick (32).

Row 7 Tutorial did nothing on stage 3 (not looked into; the Option screen has a tutorial switch).

Skills: the skill gauge is explained in-fight from stage 3 on, seen at 70% in `skill_gauge`. **No cut-in has been seen.** Every enemy-phase fight opens pairs from the cut-in range (308/309, 322/323, 330/331, 336/337, 342/343), so it preloads them. Leads: gauge reaching 100%, or a button during the fight (Circle does nothing visible). Not tried: Triangle, Square, Cross during a fight; finding the gauge in RAM.

**Stage outcome:** mode 7 reads story flag 0xA (0x54E0.. at 0x40C0) and jumps through the table at 0x1CA468: 2 game over, 3 next stage, 4 stage clear, 5 next chapter, 8 credits. Mode 15 does not read it, so `gu.outcome(v)` sets the flag and forces mode 7. **A forced game over crashes about 200 frames in** (mode 11, null read at 0xA235C, a draw called from 0x3380), so `Retry` and `Return to Title` are drawn but not exercised. Likely cause, not proven: nothing set the defeated character at seg1 +0x896A0, which 0x12A188 reads when a1 is 0xFFFF. Ending turns does not lose the stage: 15 turns on stage 3 used no cards up.

Title rows work in mode 2: LOAD DATA and CONTINUE are system dialogs, OPTION and DATA INSTALL are drawn there too.

**EXTRA (open):** mode 4 is handler 0x13FDB8, state byte at +0x98, written from title states near 0x132C9C and 0x1330B8 and from 0x13437C (end of credits) and 0x86188 when flag 0x400 of 0x8ABA638 is set. Forcing mode 4 from the title crashes: its work struct has not been set up. 0xAB840 runs before the 0x86188 path and 0x1335A8 before the credits path; one of them may be the setup. Whether mode 4 is EXTRA at all is a guess from the credits returning there. Ship screens (modes 23-25, reached from 0xD2E78, 0xD2F2C, 0xD2FE4 inside mode 20) have no route either; they probably need a unit with a ship.

## Debug-log noise

The game prints Shift-JIS to the debug log. PPSSPP forwards it as a WebSocket `log` event that is not valid UTF-8, which kills `psp.py`'s reader: `tools/debug/gu.py` wraps it.
