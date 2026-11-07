# Disc and containers

Game: Gloria Union, ULJM05813, disc version 1.01, Sting/Atlus 2011. Dump SHA-1 in `rom.sha1`.

## ISO (verified: `tools/pgd.py`, `tests/test_formats.py`)

| LBA | Size | Path | Note |
|---|---|---|---|
| 55216 | 23463 | /PSP_GAME/ICON0.PNG | XMB icon |
| 61728 | 424677840 | /PSP_GAME/INSDIR/DATA.DNS | everything: PGD around a CPK |
| 269104 | 15796 | /PSP_GAME/INSDIR/ICON0.PNG | install icon |
| 55312 | 560 | /PSP_GAME/PARAM.SFO | TITLE 'Gloria Union' is already English |
| 55232 | 157372 | /PSP_GAME/PIC1.PNG | XMB background |
| 55328 | 3905392 | /PSP_GAME/SYSDIR/BOOT.BIN | zero-filled |
| 544 | 3905728 | /PSP_GAME/SYSDIR/EBOOT.BIN | `~PSP`, encrypted |
| 32 | 880 | /PSP_GAME/SYSDIR/OPNSSMP.BIN | `~PSP` |
| 6576.. | | /PSP_GAME/SYSDIR/UPDATE/ | firmware update; never touch |
| 57248 | 9150464 | /PSP_GAME/USRDIR/Movie/GloriaUnion.pmf | opening movie (no subtitles expected, logo is English; check in phase 8) |

Free space: `iso9660.patch` appends a grown file at the end of the image and repoints the record, so DATA.DNS may grow (verified on PPSSPP: a 1038 MB image boots; a real UMD limit does not apply to an ISO on memory stick, not checked).

## EBOOT (verified: dumped decrypted with PPSSPP `DumpFileTypes = 7`, kept at `work/re/eboot.elf`)

Plain PRX: e_type 0xFFA0, MIPS, two PT_LOAD (text+rodata+data vaddr 0, filesz 0x300588; cplinit+bss vaddr 0x300588, memsz 0x9FBC5) plus a 0x700000A0 reloc segment of 0xB82A8 bytes at file 0x3008F0. Sections: .text 0..0x1C947C, .rodata 0x1CA170 (size 0xEC480), .data 0x2B65F0 (size 0x49ED7), .bss from 0x300800 (size 0x9F94D). File offset = vaddr + 0xA0 up to .data. No sceLibFont import: fonts are in the data.

## PGD (DATA.DNS) (verified: decrypts, MAC_0x80 checks, the plaintext is a valid CPK)

`\0PGD`, key_index 1, drm_type 1 (mac type 1, cipher type 1). vkey is derived from the MAC at 0x70, so no game key is needed: `3765bf9b93374a501710646de3440021`. data_size 0x18EC5FB6, block 0x400, data offset 0x90, hash table after the data. The cipher is a seekable stream: `tools/pgd.py`. Ported from PPSSPP `ext/libkirk/amctrl.c`.

The game opens `ms0:/PSP/SAVEDATA/ULJM05813GloriaUnion.Ins/DATA.DNS` when installed, else `disc0:/PSP_GAME/INSDIR/DATA.DNS` (strings at 0x25DAE4, 0x25DB18). **A player's old install wins over a patched disc: the README must say to delete it.**

Rebuild (verified: `pgd.build`, `tests/test_identity.py`, every byte of the original comes back): same vkey and key words 0x10-0x30; desc re-encrypted with the new data_size; data encrypted as a stream padded to 16; the table is one `mac_with(encrypted block, vkey)` per 0x400 (the last block as is, 0x3C0 here). 0x60 = MAC of the table, 0x70 = MAC of the first 0x70 bytes, both under vkey; 0x80 = MAC of the first 0x80 bytes under FKEY. The dump's 10 plain bytes between data_size and the 16-byte end are junk, kept in `pgd.TAIL`. Whether a real PSP checks the block table is not known; ours are correct either way, and a game that passes its own key still gets the same vkey.

## CPK (verified: `tests/test_formats.py`)

CPKMC2.15.00, ITOC only (no names), 2965 files, id order, Align 2048, ContentOffset 0x6800. `tools/itoc.py` lists and expands; CRILAYLA on 1415 files (`itoc.unlayla`). Rebuild: `itoc.pack(cpk, {id: bytes})`; `cpk.py rebuild` refuses ITOC-only CPKs. Ids keep their order and Align. ITOC rows: DataL (u16 id, size, extract) when both sizes are under 0x10000, else DataH (u16, u32, u32); each table sorted by id and padded to 8. ContentSize is the sum of aligned FileSizes, EnabledDataSize of FileSizes, EnabledPackedSize of ExtractSizes; the last file has no trailing pad. CRC columns are absent (TocCrc None). ITOC gap: 1896 free bytes before ContentOffset, 4 per file crossing into DataH; all 1415 compressed files stored plain still fit.

Edited files go in plain (FileSize == ExtractSize). Verified by a boot: every CRILAYLA file stored expanded (DATA.DNS 487 MB, moved to the end of the ISO), with the plain ELF as EBOOT.BIN: smoke ok, 149/149 warp scenes, shots of 3 screens clean. So no CRILAYLA compressor is needed, at the cost of a larger image only.

## File map (by CPK id, magic of the expanded file)

| Ids | Magic | What |
|---|---|---|
| 0 | FCT | 5 sections: BE-offset table + 4 RIFF sounds |
| 1 | FCT | FORM/EXIF + PTP (35 textures) |
| 2, 4, 160, 1582-2433 | PTP | texture packs (count at +4, offsets from +0x10) |
| 3 | FCT | core UI: fonts, digits, button labels, windows, sec 15 = common text (`text.md`) |
| 5, 1383.. | RIFF | sound effects |
| 6-208, 1034-1326, 1470.. | PTG@ / PTA | sprite/animation sets (PTG embeds a PTX; PTA = animation with textures) |
| 212-232 | FCT | two 512x256 pages each, see `graphics.md` |
| 405-1007 | BE offset table | 603 files, 38 MB, unexplored; no PTX or text in them (guess: map or battle data) |
| 1008-1420 | ADX (0x8000) | BGM and jingles |
| 1652-1702 | FPD | 3 tables + PTX |
| 1759-1849 | 0x1E02 + zeros | 91 small tables, unexplored; no text |
| 1926-1944 | PNG | 19 PNGs, see `graphics.md` |
| 2032-2082 | size table | story scripts (`text.md`) |
| 2083-2361 | VPD | 279 voice packs, 108 MB: u32 count at +4, then (id, offset) pairs of ADX; no images |
| 2420-2434, 2579-2637 | FCT | ADX banks (every section is ADX), no images |
| 2666-2964 | ADX (0x20) | voices (299 files) |

FCT: `FCT\0`, u32 count, u32 header (0x10), pad; then (u32 offset, u32 size) per section, relative to the FCT's start; nests.
