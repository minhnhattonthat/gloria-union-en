# Status

Updated at the end of every session. Keep it to what the next session needs; history is in git.

- **Phase:** 2. Debug tool in progress (phase 1 met, not started). Last build: none.
- **Done:**
  - Phase 1 graphics survey: `docs/re/graphics.md`, 3073 images in 64 sheets. Read by one reader (codex was over its limit until 2026-11-11), about half the sheets full size, the rest at quarter or half scale: no independent pass; see that file for exactly what was read. `tools/ptx.py` gained `ptg()` compositing, shared palettes and a grey fallback; `tools/survey.py` rewritten.
  - Names: no English release exists, so the game's own plates are official. Binding list in `glossary.md`.
  - Step 0: template filled, hooks (`core.hooksPath tools/hooks`), `tools/check.py`, dump pinned, guard hook blocks `sed -i` (seen live), a failing test rejects a commit, smoke boots the original to the title, a scripted circle press changes the screen.
  - Recon: `docs/re/disc-and-containers.md`, `text.md`, `graphics.md`. DATA.DNS decrypted (`tools/pgd.py`), CPK by id (`tools/itoc.py`), PTX decoder (`tools/ptx.py`), script reader (`tools/vm.py`).
  - Search found no earlier English patch for this game.
- **Next:**
  1. Working files are present on this machine (`work/iso`, `work/re`). On a clean clone: `iso9660.py x` into `work/iso`, the two unpack commands in AGENTS.md, then copy `tools/ppsspp/memstick/PSP/SYSTEM/DUMP/ULJM05813_EBOOT.BIN` to `work/re/eboot.elf` (else `DumpFileTypes = 7`, boot windowed, set back to 0). Survey sheets: `python -X utf8 tools/survey.py work/re/survey`.
  2. Phase 2 (debug tool). PPSSPP has no Lua: drive RAM through `psp.py` or CWCheat. Scene list must include every chapter card, stage intro page, game over, the ending letters, credits, EXTRA menu, tutorial plates and a skill cut-in: all of those are images (`docs/re/graphics.md`).
  3. If codex is back (after 2026-11-11), a second read of the survey sheets is worth one run: `work/re/survey/prompt.txt` is the brief.
- **Open bugs:** none yet.
- **Open RE questions (non-blocking):** see `docs/re/text.md`: op 0x74 inline team names (rewriting shifts code); next-page strings; script load-buffer limit; PGD rebuild. `docs/re/graphics.md`: VWF needs the draw routine; PTG composites show junk in the last rows (fix before writing PTGs); PTA vertex tables undecoded, so whether PTA holds text is unknown.
- **Not checked:** keyboard input in the windowed PPSSPP (Step 0 asks for it; the headless pipeline does not depend on it).
- **Waiting on the user:** nothing blocking. Real-hardware note: a plain ELF EBOOT runs on PPSSPP and CFW only; default is to ship it that way unless told otherwise. English already in the game's textures has typos and odd phrasing (SKELTON, `To The Victry`, `The Girl Are My Bride!!`): default is to fix a typo only in a texture being redrawn anyway, and leave the rest; say if you want them all cleaned. Scope warning: story pages, ending letters and tutorials are images, so phase 5 carries much more graphics work than usual.
