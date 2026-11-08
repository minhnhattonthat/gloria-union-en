# Text

Encoding everywhere: **Shift-JIS (cp932)**. No table needed for extraction. Line break: byte `0x01`, shown as a newline in `script/`. EBOOT strings can also hold a real `\n`, shown as `[0A]`, and printf codes (`%d`, `%s`; count and order must stay).

`tools/extract.py` writes `script/`; `tests/test_extract.py` proves it (below). Counts: 19,538 entries, 19,367 to translate, 326,149 characters, 13,194 unique strings.

| Where | To translate | Unique | Characters | `script/` |
|---|---|---|---|---|
| Story scripts, ids 2032-2082 | 7,355 (180 team names) | 6,688 | 162,882 | `story/<id>.json` |
| Common text, id 3 section 15 | 1,472 | 1,447 | 36,573 | `common/sub<n>.json` |
| EBOOT | 10,540 (plus 171 not text) | 5,106 | 126,694 | `eboot/<group>.json` |

## VM scripts (verified: `tools/vm.py` names every byte of all 51 files and of common subs 0-4, 7-9)

Handler table at 0x2EF748. Instruction: `<op> <total length> <args>`, at most 40 bytes, so a second byte over 40 means text. Exceptions, read from the handlers:

- `74 05 <side> <name> 00`: the handler (0x11C020) ignores the 05, uses strlen, and stores a **pointer to the string in the script** in a per-side struct of 0x90 bytes in .bss. 180 sites, all in `story/`.
- `52 02` + 5 u32 targets, `53 02` + 3 u32 targets: goto indexed by save byte +0x1A9, +0x1A4.
- `06 02` is **return**, so anything may follow: 0x90 or 0x00 padding to a 4-aligned address, then sometimes a u32 target table (at least 2 entries).

Text span: optional `02 00 <u16 voice id>` tag, cp932, NUL. The line counter at 0x119BD0 skips 4 bytes on 02 and treats 03-1F as 2-byte codes, but no script text holds any such code (every string decodes to printable text plus 0x01). 3,943 strings carry a tag. 0x90 pads between spans. Script 2042 has one tag with no text in front of a message at 0x7B5: a `pad` span.

**Message: `46 07 00 <u32 offset of the text>`** (8,336 sites, sub-op 0). `46 05 02 <u16>` plays voice id + 0x823 (sub-op 2), `46 03 03` waits for it, `46 03 01` once. Earlier notes called these next-page forms: wrong, they are voice.

**39 story strings and 5 common ones have no pointer** (`slots: []`). No u32 in any instruction or table holds their offset. They read as conditional NPC lines. Likely dead; the marker build decides. Translate them anyway. The earlier "next page" guess is dropped: nothing reads a string by adjacency as far as the handlers go, though the display path past 0x119E30 was not read to the end.

**Speaker:** the last `eb 0b <side> <expr> <u16 char> ...` before a message. Ids 0-0x0E index the name table at 0x2C8748 (verified); higher ids follow the unit name pool at 0x2808F0 with team forms dropped (guess; a sample of lines per id reads right). 0x0F has 87 lines and no name. Ids of 0x1D and up stay `#<id>`. `who` in `script/` is translator context only, never inserted.

**Insertion (`tools/insert.py`, `tests/test_insert.py`):** code keeps its offsets. The old text spans are zeroed and reused first-fit (longest text first), the rest is appended after the end; each slot in `slots` is rewritten. Tags stay with their text. Common subs grow the same way and id 3 is rebuilt through two FCT levels (`insert.fct_pack`, 16-byte alignment; no edits give the original). EBOOT: a string that fits its bytes stays, else it moves to the blob and its `w:` words / `i:` lui+lo pairs are rewritten (a lui shared by several lo's of one string is written once; the build asserts no lui is shared between strings and no lo is `ori`). Load buffer limit: the marker build (every script grown) played every stage warp: see status.

**Team names (op 0x74):** in `script/` with `at` and `max` (4-20 bytes, 47 unique names). **Dead (read from the handler, phase 5):** 0x11C020 stores the return of `jal 0x11c018`, which is `jr ra; move v0, zero`, so the side's name pointer is always 0; the string only sets how far the script skips (strlen). The build writes English in place cut to `max`; no hook. Not checked at runtime.

## Text renderer (phase 5, verified: read breakpoint on a stage 3 message, hooks on the glyph setter)

All text goes through one **writer at 0xA222C** (205 callers). Args: a0 window, a1 col, a2 row, a3 colour, t0 font (16+ = font - 16 with a colour from the table at RAM 0x8B910F0 + 12 * (font - 16) + 8), t1 text, t3 one-char mode (the typewriter at 0xA2900 calls it per character and keeps col/row at globals lui 6 +0x5CB8/+0x5CBA). Returns the text pointer.

- **Windows** are grids of cells: +0/+2 x, y; +4/+6 box size; +8/+A extra spacing x/y; +C/+E offset; +14 cell array; +18/+1A cols, rows; +1C/+1E cell size from the table at 0x2BE4AA by font; +34 flags; +98 sprite list. `setSize(win, cols, rows)` at 0xA3C5C allocates cols * rows cells of 0x24 bytes and (rows + 5) * cols sprites of 0x20. Dialogue: font 1, 16 cols x 3 rows, cell 20x20, spacing -2, +2, box 288 px wide. Name tag: font 3, 15 cols, cell 24x24.
- **Cell** (0x24): +0 col, +2 row, +4/+6 screen size, +8 colour (0 = empty), +C/+E u, v, +10/+12 uv size, +14 texture, +1E flags (bit 0: +0/+2 are absolute pixels; the writer clears it), +20 from the caller.
- Text bytes: 00 end; 01 newline (row + 1, col 0); 02 `u16` voice; 03 `<b>` and 04 `<u16>` call an indexed string from the table at lui 9 -0x349C (push return); 20-7F ASCII; 80+ Shift-JIS pairs. No auto-wrap: a col past cols - 1 is not drawn.
- **ASCII:** font 0 draws it from its own 8x8 sheet. Other fonts map it through the table at 0x2BE3E8 (0x20-0x7F to fullwidth: space to 0x8140, `\` to ￥) and look the code up (0xA1FB8). Before that, `!?`, `!!`, `Lv`, `r.` become glyphs 0x22, 0x23, 0x29, 0x2F (code at 0xA2648-0xA26C8): a VWF build must skip those checks.
- **Tables that decode as text** (verified 2026-11-08: font 4 drew `.`→ソ, `0`→チ until fixed): 0x2BE3CA bucket splits, 0x2BE3E8 the ASCII→fullwidth map, 0x2BE4BE font 4's 180 codes (lookup 0xA1F60), 0x253874 `０１２…９　` (0xA36B0 turns sprintf'd digits into fullwidth, e.g. the unit count drawn at col 15 beside a font 4 unit name), and 11 strings holding 0xFF bytes (-1 filled tables). Extraction had them as text, so marker builds overwrote them; `extract.py` now marks them `data` (NOT_TEXT, and any 0xFF byte = binary).
- Glyph 0 (0x8140, fullwidth space) skips the glyph setter (0xA274C, 0xA2810), so a space cell keeps colour but no texture.
- **Glyph setter 0xA20E4** (a0 window, a1 font, a2 glyph, a3 cell): u, v, uv size and texture from the font header; called only from 0xA2764, 0xA2828, 0xA2844.
- **Sprite builder 0xA2FD0**: x = col * (cell w + win+8) + win+0 + win+C (at 0xA31A4-0xA31DC); y likewise with rows; sprite right edge = x + cell +4, so a narrower +4 and +10 crops a glyph.

**VWF (built, `tools/vwf.py`, booted: stage 3 talk, tutorial, name tags):** the spare-cell plan was dropped: font A's last page is only 180 px tall (4 spare cells), so ASCII glyphs live in **three new PTX sheets in the EBOOT blob** (one per engine font 1-3), stored in their loaded form (byte 3 = 1, +0x18/+0x1C absolute, made so by R_MIPS_32 relocations). A cell's texture (+14) is just a pointer to a PTX header, so a glyph can come from any sheet. PTX +0x14 is `15 - log2 w, 15 - log2 h, 0x11, 0` (from 30k textures).
- 0xA2648 `b 0xa26d4`: no ligatures. 0xA26FC `jal asc`: fonts 1-3 map ASCII c to glyph 0x8000 | c, other fonts go on to 0xA1FB8.
- The 3 setter calls go to `wrap`: glyph & 0x8000 takes u, v, size and texture from our sheet and its width table (draw width, advance = draw width - 1: outlines overlap); other glyphs go through 0xA20E4 with advance = cell w + window spacing. Then cell +0 = pixel x: previous cell's x + its advance, or the grid x (col * (cell w + spacing)) when col is 0 or the previous cell is not VWF or has no texture, so fixed-column fields keep their original x. +1E: 0x8000 VWF, bits 8-13 advance, 0x4000 placed by `chain`. The writer's flag reset (0xA25B0) now keeps only bits 1-7.
- Sprite builder 0xA31A4 `jal bstub`: with 0x8000, x = +0 + window x + offset; bit 0 (absolute) still wins.
- **Re-layout helpers** 0xA3D74 (entry; args a0 win, a1 col, a2 row, a3 x, t0 y, t1 cols (0 = rest of row), t2 rows, t3 font; about 110 callers) and 0xA3F54 (same plus stack spacing): put each coloured, textured cell at an absolute x (bit 0), x += cell +4 (+ spacing). Menus call them per cell for the original column count at their own pitch: title OPTION (0x12EB3C) places 10 cells a row 18 px apart and fades them in (0xA4370), so English drew at grid columns and cells 10+ at the window origin. **Fix, `chain` at 0xA3188 in the builder:** a VWF cell at col > 0 whose previous cell is VWF, absolute, coloured and textured gets x = previous x + previous advance; if the menu didn't place it (not absolute) or chain did (0x4000), it also takes the previous y and becomes absolute. Cells 10+ of the OPTION rows skip the fade (widening its loop to 30 hid them).
- **Palette alpha:** the PTX loader sets alpha 0 on magenta palette entries (every loaded PTX in RAM has `ff00ff00`; files have `ff00ffff`). Our sheets are stored already loaded, so `vwf.ptx_loaded` zeroes it itself; without that, every window except dialogue (font 17, which takes another colour path) drew a magenta box behind each English glyph.
- **Code that sizes text by byte count** (verified 2026-11-08 on battle_result and stage_3_07_B): the width helper 0xA4A3C(win, count, font) = count x (cell w + win+8); six callers pass strlen / 2 to right-align or centre a string (unit name bar 0x7404 right-aligns at x 211; 0xB7C70; map headers 0xC198C, 0xC1A80, 0xC1B0C, 0xC1C08); their strlen calls go through `vlen` (remembers the string at blob data +64) and the helper call through `vwidth` (VWF advances for ASCII, the pitch per SJIS char, half a pitch for ASCII in fonts without a sheet). The other 11 callers pass constant counts (fixed field positions) and are left alone. The battle bark bubble (0x4C238) keeps strlen / 2 at +0x208 as its cell count (bubble size, centring): that strlen goes through `vcells` (2 x the font 1 width in 20 px cells, rounded up). The stage intro win/lose conditions (layout loop 0x143E10, windows at x 480, 30 cells a row) placed SJIS cells and only the bytes `o`, `r` (of "イシュトorピンガー") absolutely; 0x1440B8 is now a nop so every ASCII byte takes the `o` path and `chain` spaces the rest. Other places that measure text by bytes may exist: a tour shot with text off-centre or cut at the left points at one.
- setSize 0xA3C94 `jal cols3`: 3x columns for every window (col limit and memory; positions don't depend on cols).
- Glyphs: `fonts/MPLUSRounded1c-ExtraBold.ttf` (docs/fonts.md), 1 px black outline, each font's own palette (key colour magenta: index 0 in A and B, 15 in C). Dialogue averages about 8 px a character: `vwf.line_px()` measures a line as the engine lays it out.

## EBOOT growth (`tools/eboot.py`, selftest: no edits gives the original)

Segment 1 is .bss only. The build gives it file bytes for all of .bss (zeros) and appends a blob (new code, strings, tables) at vaddr 0x3A0150; the relocation segment moves back. RAM = 0x8804000 + vaddr for both segments, so a pointer into the blob is its vaddr with address base 0, like any pointer into segment 0: moved strings need no new relocations, only new word values. New code reaches game functions by `jal` (the builder adds an R_MIPS_26 relocation) and blob data by `bal`. **PPSSPP applies the `.rel` sections, not the relocation segment**, so new entries extend both (`.rel.linkonce.d` is last). Booted: a 512 KB blob plus `setSize` routed through a blob stub reaches the stage 3 warp at the same frame as the original (`warp.py stage_1_02_AP`), and RAM shows both jumps relocated. keystone needs `.set noreorder` (else it adds a nop after every jump) and named labels.

## Common text: id 3 section 15 (nested FCT, 10 subs) (verified: all parse)

All but 5 and 6 are VM code. Offsets in slots are relative to the sub's start. The "Holds" column comes from reading a sample of each sub.

| Sub | Size | Holds | Entries |
|---|---|---|---|
| 0 | 0x26EA | u32 table + code: defeat lines, one routine per character | 76 |
| 1 | 0x583 | ballista and cannon crews | 13 |
| 2 | 0x6A74 | item pick-up lines | 16 |
| 3 | 0x841 | sleeping-crew lines | 33 |
| 4 | 0x26C36 | code, no text | 0 |
| 5, 6 | 0x160, 0x1B1 | bare strings: sleep and petrify remarks. **Reader not found** | 14, 17 |
| 7 | 0x65C0 | story layout: u32 end, 0x90 fill, code; tutorial talk; a 23-entry offset table after end | 320 |
| 8 | 0x1E321 | u32 table + code: item-use lines per character | 977 |
| 9 | 0x275 | out-of-cards lines | 6 |

Other sections of id 3 have no text: the `textsweep.py` sentence test finds no run in id 3 outside section 15 (one-off check). Growing a sub means rebuilding two FCT levels, or hooking the loader: phase 5.

## EBOOT (verified: test, every entry re-encodes in place and each `w:` slot holds its address)

Plain PRX; file offset = vaddr + 0xA0. `tools/elf.py` parses the three .rel sections: `R_MIPS_32` words (mostly (id, pointer) pairs at stride 8 in .rodata tables, read by eye on a sample of the tables) and `lui`/`lo` pairs in code, paired by register in reloc order. An entry in `script/eboot/` has every reference found in `slots`: `w:<word vaddr>` or `i:<lui vaddr>:<lo vaddr>`. 75 strings to translate have an `i:` slot. The test checks that each pair adds up to the address, not that the pair runs together: a `lui` reused across a branch could pair wrongly, so phase 5 confirms them when strings move.

Groups by address (names from reading a sample): `messages` skill refusals; `barks`, `barks2` battle lines by class and situation; `chants` skill incantations; `ui1-3`, `items`, `names`, `saves`; `data` is .data: stage hints, skill names, map names and descriptions, class names, biographies (these too are pointed at, not inline). Strings repeat a lot, each copy at its own address, so the batch tool must dedupe: 5,106 unique of 10,540.

`status: data` marks 171 strings players never see: debug text (`メインスレッド一時停止`), binary that decodes, and a glyph list at 0x2537C0 (`NOT_TEXT` in `extract.py`; the glyph list's reader was not traced, so check it in phase 5). Debug and binary were picked by address from a listing of odd strings, not proved unreachable. Filters in `elf.text()`: half-width kana, a lone kanji plus a stray byte, runs of 0x01. Code pointing into the middle of a run is a struct base, not a string.

**Format buffers (`tools/fmtbuf.py` -> `tbl/fmtbuf.tsv`; enforced by `insert.Inserter.text`, `tests/test_insert.py::test_format_buffers`):** some %-strings are `sprintf` (0x14E3B0) into stack buffers. `%2d戦%2d勝` (e:1edc5c, battle_result) goes to sp+0x130 with a local at sp+0x140: 15 bytes of output. Its marker made 20 and crashed the emulator at the result screen (found by bisecting `--only` prefixes with `tools/debug/markbisect.py`). The limit per string is the gap to the next $sp offset the function touches (heuristic: too small at worst; where the original's own output is longer, its length is used). A text over its limit fails the build; a marker over it becomes `[id]` + codes or stays Japanese. Not traced: `%sの士気が`/`%sの経験値は`/`%s隊` (no sprintf after the lo; another formatter), the save-dialog strings (`w:` slots, sceUtility buffers), and strcpy-style copies of plain strings. Traced by hand: `＋` `－` `　` (e:1ed9a0/a4/a8) are sprintf'd alone into sp+0x44 (16 bytes) and `%d％`'s output (sp+0x5c) is strcat'd (0x14F170) after them, so each prefix gets 16 - 1 - 5 = 10 bytes (`fmtbuf.py` adds these rows; `stress.py --fit` leaves byte-limited entries as markers).

**Plain strings through `%s` into stack buffers** (2026-11-08; the fit build crashed `extra_item/music/audio_drama/scenario`, all four pass once these limits apply: `work/qa/extra3`): EXTRA list rows are `sprintf(sp+0x10, "%02d %s", n, title)` into 32 bytes (locals at sp+0x30 are reloaded per row), so a title gets 28 bytes: scenario titles (table 0x2F6D6C, 0x18 a row, +4; 0x1364A4), music (0x2F8090, 0x10, +8; 0x13C3D8), audio drama (0x2F8450, 0x10, +8; 0x13D538), card names (0x2BCFCC, 12, +0, via 0x89024; card list 0x1390AC). Item names: EXTRA item page `sprintf(sp+0x10, "%s", name)` into 36 bytes (0x13A87C; names 0x2CD2E8, 4 a row): 35. Card detail (0x139650): the effect (0x2BCA28, 12, +0) is strcpy'd into 60 bytes then each line `"・%s"` into another 60; the condition (+8) goes through `"・%s"`: 57 each. `tools/fmtbuf.py` `TABLES` writes these rows to `tbl/fmtbuf.tsv` (526 rows), so `insert.py` enforces them like the printf limits. Other `%s` sprintf sites exist (pcts scan: ~100 calls, most with formats not resolved by a lui/addiu pair, e.g. 0xD0614 `%s%s` into 40 bytes, 0xEFF24, 0xC13E8...): not traced; a crash in a later sweep with real text points at one.

**Item descriptions** (0x2CCAB0 and 0x2CCECC, 261 pointers each, same strings): no newlines in the Japanese. Three screens write the text as one row and place its cells by hand (0xA3D74 per cell), starting a new line at a break cell read from a per-item table: the item screens 0xE0FE8 and 0xE11CC (font 1, x 24 + 18 a cell, line 2 at +20; table 0x2CA458, 1 byte per item: 2 lines) and the EXTRA item page 0x13A87C (font 2, x 298, line pitch 18; table 0x2F86F0, 2 bytes per item: 3 lines). They placed only 30 cells; now 90 (`vwf.py`, slti at 0xE1170, 0xE1308, 0x13AA10). A `\n` in the text sends the rest to row 1, which no loop places: `insert.py` replaces newlines with spaces and writes both break tables from a word wrap per screen (`desc_breaks`, `DESC_FIT`: EXTRA 3 x 134 px font 2, measured `work/qa/itemdesc2/z.png`, panel text ends before the dotted strip at ~x 432; item screens 2 x 234 px font 1, read from code, not shot: no route gives the party items). `chain` used to put a hand-placed cell after its VWF neighbour even when the menu had moved it to a new line (line 2 started where line 1 ended); it now keeps the menu's x when the cell's y differs from its neighbour's. An English build fails on a description over its lines.

`id 1` holds `ＥＦ＿０１２＿ネクロゲート`-style labels in its EFCS block: development names of effects, not shown.

## Coverage (`tests/test_extract.py`, runs on every commit; 3 deliberate corruptions each made it fail)

- Spans cover every byte of every script block.
- Every text span re-encodes from `script/` to its exact bytes, tag included, and each slot holds the offset.
- Every message op targets a text span.
- No kana in op or table spans except op 0x74.
- EBOOT: every cp932 run with 2+ kana or 3+ kanji in .rodata and .data is an entry, or one of 12 addresses read by eye as binary.
- `extract.py` refuses to run over `script/`.

**Other files** (`tools/textsweep.py`, one-off, every expanded CPK file except the text ids and audio, in cp932, UTF-8 and UTF-16LE): 43 hits, all cp932, none UTF. All are image or table bytes that decode by chance (PTG, FPD, PTP, PTX, the FCT pages 213-232), plus id 1's effect labels. So text is only in the story scripts, id 3 section 15 and the EBOOT. Text drawn as pictures is in `graphics.md`.

## Free space

- ISO: unlimited (append). DATA.DNS: file grows; ok. Script files: append after the trailer.
- EBOOT: 0x48 file bytes spare at most; relocate strings into a new segment past .bss (phase 5). No slack verified.
