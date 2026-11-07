# Text

Encoding everywhere: **Shift-JIS (cp932)** (verified: every extracted run reads as Japanese sentences). No table needed for extraction. Line break in text: byte `0x01` (scripts, common text). EBOOT strings use `\n` and printf codes (`%d`, `%s`; count and order must stay).

## Story scripts: CPK ids 2032-2082 (51 files) (verified: `tools/vm.py` and the sweep below)

Layout: u32 end_of_code; u32 entry points (count varies: read until a value is not an offset); then blocks of text and code **interleaved** in file order; at end_of_code a 0x14-byte trailer (`04 00 ...`).

- Text record: `02 00 <u16 id> <cp932> 00`, or a bare `<cp932> 00`. `id` runs up through a file; it is the voice line number (guess: voices are ids 2666+).
- Code: `<op> <total length> <args>`. Exceptions: op 0x74 has `74 05 <side>` then an inline NUL-terminated team name; there are switch tables with raw u32 targets, so a linear walk needs more ops (see `vm.walk`, it stops on these; not needed for text work).
- **Text reference: `46 07 <speaker u8> <u32 absolute file offset of the record>`.** 7136 records, 315,263 bytes of SJIS, all decode cleanly, zero bad starts (sweep over `b'F\x07'`).
- **Next-page strings have no pointer.** A bare string directly after a referenced record is the next page, reached by the short forms `46 03 ..` / `46 05 ..` (guess from the op lengths; about 40 such strings seen; confirm in phase 5 with the marker build). Keep record order inside a block when re-emitting.
- Inline team names (`イシュト海賊団`, `ベルガス一味`...): 68+ op 0x74 sites, shown on the battle intro. Rewriting one shifts code, so branches would need fixing; phase 4 option: repoint or keep the length (their bytes are 7 to 8 full-width chars, English must fit or the walker must be finished). Battle-intro strings may also be overridable. **Open question for phase 4.**
- `90 90` filler bytes occur before some strings (0x2032:0xC12).

**Plan for growth:** code keeps its offsets. Write English into a new text block appended after the trailer (keeping page order), rewrite each `46 07` offset, update the file size in the CPK. No code bytes move. Load buffer limit: unknown, check in phase 5 with a grown file; the largest original is 53,880 bytes (id 2057).

## Common text: id 3, section 15 (offset 0x450E90 in the expanded file, a nested FCT of 10 sections)

Pairs of offset table + strings, plus one script block.

| Sub | Offset | Size | Holds |
|---|---|---|---|
| 0 | 0x60 | 0x26EA | offset table then strings (236 entries): game-over and defeat lines by character |
| 1 | 0x2750 | 0x583 | u32 offsets + strings |
| 2 | 0x2CE0 | 0x6A74 | u32 offsets + strings |
| 3 | 0x9760 | 0x841 | u32 offsets + strings |
| 4 | 0x9FB0 | 0x26C36 | u32 offsets + strings (largest; likely unit/card lines) |
| 5, 6 | 0x30BF0, 0x30D50 | 0x160, 0x1B1 | bare strings |
| 7 | 0x30F10 | 0x65C0 | code-like block with `90 90` filler (`de\0\0` magic) |
| 8 | 0x374D0 | 0x1E321 | u32 offsets + strings |
| 9 | 0x55800 | 0x275 | u32 offsets + strings |

Other id 3 sections 2 (0xD8020, 0x7EA8) and 17 (0x4B3010, 0x1588) are u32 tables; 8 and 9 are tables with no text. Exact semantics: phase 4.

## EBOOT strings

Japanese runs in .rodata from about 0x1E0000 to 0x25FFFF (file offsets; 0x1F0000-0x25FFFF holds ~9,500 hits), about 280 KB including noise. Skill messages, unit, item and skill names, descriptions. Earlier hits (below 0x1C0000) are code noise. .data holds no sentences, but its tables point into .rodata.

**Pointers (guess, verified only for the format):** the PRX is relocatable, so every absolute reference to a string is listed in the 0x700000A0 reloc sections (.rel.text 0x76F40 bytes, .rel.rodata 0x34720, .rel.data 0xC738): `lui`/`addiu` pairs and data words. Parse these in phase 4 to get each string's references; that is the slot list. Strings can then move into a new loaded region at the end of the image, with only the instruction or word changed (a plain ELF EBOOT runs on PPSSPP and CFW; phase 5 decides). Script text never goes through the EBOOT.

## Free space

- ISO: unlimited (append).
- DATA.DNS: file grows; ok.
- Script files: append after the trailer.
- EBOOT: 0x48 file bytes spare at most; relocate strings into a new segment past .bss (phase 5). No slack verified.
