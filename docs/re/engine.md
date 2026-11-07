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

## Pre-battle flow (open)

Stage 1: story, then Character Select (mode 20), Circle on a character goes to Card Select (mode 26). In Card Select: Down to a card row, Circle enters it (1/5, Total Move 12), Cross releases, Square returns to mode 20, Right from mode 20 opens the morale tab (mode 22). **Not found: the input that starts the battle.** Tried without effect: Start, Select, L, R, Circle on the rows, Down past the last row. Forcing mode 16 from mode 26 crashes. Leads: mode 16 is written at 0xD2B5C (mode 26 path) and 0xDF9E8 (mode 20 path, after a fade test at 0xDF990, `jal 0xDEF68`, `jal 0xDD04C`).

## Debug-log noise

The game prints Shift-JIS to the debug log. PPSSPP forwards it as a WebSocket `log` event that is not valid UTF-8, which kills `psp.py`'s reader: `tools/debug/gu.py` wraps it.
