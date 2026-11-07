# Status

Updated at the end of every session. Keep it to what the next session needs; history is in git.

- **Phase:** 2. Debug tool in progress: stages, cards, credits and letters warp; battle entry, game over, EXTRA and skill cut-in not reached yet. Last build: none.
- **Done:**
  - Phase 2 so far: `tools/debug/gu.py` (session, breakpoint hooks, RAM), `scenes.py` (scene list), `warp.py` (`warp.py SCENE`, `--all`; results in `work/qa/warp/results.tsv`). The warp rewrites the argument of the game's own `loadStage` after New Game, so chapter cards and intros play as usual. Engine facts: `docs/re/engine.md`.
  - Sweep on the original ISO: 105 of 106 scenes reached from a cold boot; `card_select` failed there, then passed alone after a fade wait was added. The full sweep was not rerun after that fix.
  - **How strong that proof is:** a stage counts as reached when its script file opens and the shot 180 frames later is not flat. Stages sharing a script (the `P` variants, 21 of the 91 by script count) are not told apart by that, and of 16 proof shots sampled, about half show the sea-chart transition rather than the stage. 84 of 91 stage shots are distinct. A stricter proof should assert `save+0x1A0` or the loaded entry point. Warps run with a fresh party, so a stage may play differently from a real run: not checked.
  - Phase 1 graphics survey: `docs/re/graphics.md`, 3073 images in 64 sheets. Read by one reader (codex was over its limit until 2026-11-11), about half the sheets full size, the rest at quarter or half scale: no independent pass; see that file for exactly what was read. `tools/ptx.py` gained `ptg()` compositing, shared palettes and a grey fallback; `tools/survey.py` rewritten.
  - Names: no English release exists, so the game's own plates are official. Binding list in `glossary.md`.
  - Step 0: template filled, hooks (`core.hooksPath tools/hooks`), `tools/check.py`, dump pinned, guard hook blocks `sed -i` (seen live), a failing test rejects a commit, smoke boots the original to the title, a scripted circle press changes the screen.
  - Recon: `docs/re/disc-and-containers.md`, `text.md`, `graphics.md`. DATA.DNS decrypted (`tools/pgd.py`), CPK by id (`tools/itoc.py`), PTX decoder (`tools/ptx.py`), script reader (`tools/vm.py`).
  - Search found no earlier English patch for this game.
- **Next:**
  1. Working files are present on this machine (`work/iso`, `work/re`). On a clean clone: `iso9660.py x` into `work/iso`, the two unpack commands in AGENTS.md, then copy `tools/ppsspp/memstick/PSP/SYSTEM/DUMP/ULJM05813_EBOOT.BIN` to `work/re/eboot.elf` (else `DumpFileTypes = 7`, boot windowed, set back to 0). Survey sheets: `python -X utf8 tools/survey.py work/re/survey`.
  2. Phase 2, still missing from `tools/debug/scenes.py`: game over, EXTRA menu, skill cut-in, map menus and other in-battle screens. All need the battle started: see "Pre-battle flow (open)" in `docs/re/engine.md`, read the mode 20 path at 0xDF990 rather than trying buttons. EXTRA: title mode 4 set at 0x85310; find its unlock flag. Stage intro pages (1589-1635): confirm which stages load them.
  3. If codex is back (after 2026-11-11), a second read of the survey sheets is worth one run: `work/re/survey/prompt.txt` is the brief.
- **Open bugs:** none yet.
- **Open RE questions (non-blocking):** see `docs/re/text.md`: op 0x74 inline team names (rewriting shifts code); next-page strings; script load-buffer limit; PGD rebuild. `docs/re/graphics.md`: VWF needs the draw routine; PTG composites show junk in the last rows (fix before writing PTGs); PTA vertex tables undecoded, so whether PTA holds text is unknown.
- **Not checked:** keyboard input in the windowed PPSSPP (Step 0 asks for it; the headless pipeline does not depend on it).
- **Waiting on the user:** nothing blocking. Real-hardware note: a plain ELF EBOOT runs on PPSSPP and CFW only; default is to ship it that way unless told otherwise. English already in the game's textures has typos and odd phrasing (SKELTON, `To The Victry`, `The Girl Are My Bride!!`): default is to fix a typo only in a texture being redrawn anyway, and leave the rest; say if you want them all cleaned. Scope warning: story pages, ending letters and tutorials are images, so phase 5 carries much more graphics work than usual.
