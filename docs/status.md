# Status

Updated at the end of every session. Keep it to what the next session needs; history is in git.

- **Phase:** 1. Research and recon in progress (graphics survey left). Last build: none.
- **Done:**
  - Step 0: template filled, hooks (`core.hooksPath tools/hooks`), `tools/check.py`, dump pinned, guard hook blocks `sed -i` (seen live), a failing test rejects a commit, smoke boots the original to the title, a scripted circle press changes the screen.
  - Recon: `docs/re/disc-and-containers.md`, `text.md`, `graphics.md`. DATA.DNS decrypted (`tools/pgd.py`), CPK by id (`tools/itoc.py`), PTX decoder (`tools/ptx.py`), script reader (`tools/vm.py`).
  - Search found no earlier English patch for this game.
- **Next:**
  1. Regenerate the working files (gitignored): `iso9660.py x` into `work/iso`, then the two unpack commands in AGENTS.md; copy `tools/ppsspp/memstick/PSP/SYSTEM/DUMP/ULJM05813_EBOOT.BIN` to `work/re/eboot.elf` (present on this machine; else `DumpFileTypes = 7`, boot windowed, set back to 0).
  2. Finish the graphics survey: `python -X utf8 tools/survey.py work/re/survey --sample 6`, read the 31 sheets (one at a time, or `codex exec`; Orca workers have no subagents), fill the table in `docs/re/graphics.md` with every tile-drawn Japanese element. Include title menu, PNGs 1926-1944, FPD, VPD, ICON0/PIC1, the PMF. That meets phase 1's done-when.
  3. Then phase 2 (debug tool). PPSSPP has no Lua: drive RAM through `psp.py` or CWCheat.
  4. Look up official English names: the FHD Edition (2021) exists; check whether it shipped in English. Party names seen on the web: Ishut, Pinger, Ruru, Elisha, Zazarland, Minnesota, Grey, Locomoco, Raspberry, Fiebee, Ashley (tvtropes.org/pmwiki/pmwiki.php/Characters/GloriaUnion). Unverified; put them in `glossary.md` once confirmed.
- **Open bugs:** none yet.
- **Open RE questions (non-blocking):** see `docs/re/text.md`: op 0x74 inline team names (rewriting shifts code); next-page strings; script load-buffer limit; PGD rebuild. `docs/re/graphics.md`: VWF needs the draw routine.
- **Not checked:** keyboard input in the windowed PPSSPP (Step 0 asks for it; the headless pipeline does not depend on it).
- **Waiting on the user:** nothing blocking. Real-hardware note: a plain ELF EBOOT runs on PPSSPP and CFW only; default is to ship it that way unless told otherwise.
