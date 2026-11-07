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

**Skills (verified):** fight work is RAM 0x8B89258 (seg1 +0x84CD0): +0x1068 s16 skill gauge, full at 0xE60 (seen as 100%), +0x106E charge gauge, full at 0xE60, +0x10D3/+0x10D4 fight phase, +0x76A 2 while charging, +0x730 and +0x730+0x498 the two sides (+0x734 s16 HP). Square reaches the check at 0x19328 only if story flag 8 is 4 or more, which is why stage 3 never showed one; the check 0x4E544 returns -1 (allowed) or a message index into the table at 0x2BB820 (1: leader is not the Ace, which is what the on-screen `Can't Use Skill Now...` means). A skill of type 1 charges while Square is held and fires on release with the charge gauge full (0x19844); a short press gives `CHARGE CANCEL!`. `gu.skill()` does this with the check's result forced to -1. The card and motto are up about 270 frames after firing. Every enemy-phase fight opens pairs from the cut-in range (308/309, 322/323, 330/331, 336/337, 342/343), so the pairs are preloaded by fighter; only one skill is routed so far, the others differ by leader.

**Stage outcome:** mode 7 reads story flag 0xA (0x54E0.. at 0x40C0) and jumps through the table at 0x1CA468: 2 game over, 3 next stage, 4 stage clear, 5 next chapter, 8 credits. Mode 15 does not read it, so `gu.outcome(v)` sets the flag and forces mode 7. **The forced game over needs the defeated unit:** with RAM 0x8B8DC28 (seg1 +0x896A0) empty it crashes about 200 frames in; set to a roster id it runs, types that unit's defeat line, and `Return to Title` (Down, Circle) reaches the title. `Retry` (Circle) stays black in mode 11 from a forced game over: not looked into, it may need the snapshot a real stage start makes. Ending turns does not lose the stage, and a killed unit on stage 3 does not either.

Title rows work in mode 2: LOAD DATA and CONTINUE are system dialogs, OPTION and DATA INSTALL are drawn there too.

**Tutorial list:** map menu row 7 opens a list of the tutorials whose id bit is set in the save's bitset at +0 (0x5160); a fresh save has none, so the row seemed dead. The list's Circle plays the tutorial in mode 7 (file 2023).

**EXTRA (verified):** the sixth title row. System data pointer at RAM 0x8ABB698; +0xA3 nonzero is the clear flag (2 after a higher clear, 0x649C), which adds the row (0x1318E8, 0x131AD4) and makes New Game ask for Battle Setting first. Mode 4, work at RAM 0x8B88EA8 (seg1 +0x84920), set up by 0x13EE74, +0x98 state, +0x9B open page (row + 1). Pages are locked as `???` until the system bitsets have bits set: +0 (0x107 bits), +0x21, +0x28, +0x32, +0x3D, +0x4A. `gu.unlock()` fills them. Pages: Scenario, Character, Card, Item, Music, Audio Drama; each list has detail rows the scenes do not step through yet.

**Ship screens (open, no route):** save +0x245 nonzero is a ship stage (stage 36 `4_01_A`; 66 no, 20 goes through a game over on the way). Character Select then offers Square `船長変更` (Captain Change): state +7 goes 0x3C, 0x3D, 0x3E, then mode 23 (0x144FB0). Character Select work is RAM 0x8B8B478. The states also reach modes 24 (0x1469A0) and 25 (0x1479B4). A warped run has an empty party (`0/0`), so state 0x3C waits forever on the first unit's alpha, and forcing 0x3E, 0x47 or 0x51 kills the emulator. A route needs a real party on a ship stage; not attempted. The screens' art is listed in `docs/re/graphics.md` (id 2418).

## Debug-log noise

The game prints Shift-JIS to the debug log. PPSSPP forwards it as a WebSocket `log` event that is not valid UTF-8, which kills `psp.py`'s reader: `tools/debug/gu.py` wraps it.
