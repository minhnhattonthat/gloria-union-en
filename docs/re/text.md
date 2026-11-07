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

**Growth plan:** code keeps its offsets. Append English after the trailer, rewrite each slot in `slots`. Tags stay with their text. Load buffer limit: unknown, check in phase 5; the largest original is 53,880 bytes (id 2057).

**Team names (op 0x74):** in `script/` with `at` and `max` (4-20 bytes, 47 unique names). They sit inside code, so growing one shifts code and branches. Options for phase 5: hook 0x11C020 so the handler maps the old bytes to a new table (no code moves, recommended); fit in `max` (too tight for most); or move code (`vm.parse` finds the ops, but which u32 args are targets is not listed per op). **Open for phase 5.**

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
