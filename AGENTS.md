# Gloria Union (PSP) English translation

Skill: translate-retro-game (Claude Code: plugin, enabled in .claude/settings.json; other agents: `<SKILL_DIR>/SKILL.md`; `$SKILL` = the directory holding its SKILL.md, `python tools/skill.py` prints it). Read it before ROM, text or QA work.

Run `git config core.hooksPath tools/hooks` once per clone.

## Commands (run from repo root)
- Build:    `python -X utf8 build.py` -> build/gloria_en.iso (not written yet: phase 3; checks the dump against `rom.sha1` first)
- Check:    `python -X utf8 tools/check.py` (tests + lint; the pre-commit hook runs this)
- Smoke:    `python -X utf8 $SKILL/scripts/emu.py build/gloria_en.iso --out work/qa/smoke --route tools/routes/boot.txt --smoke`
- Warp:     `python -X utf8 tools/debug/warp.py SCENE [--state-out F]`, `--all [--match stage_]` (PPSSPP has no Lua; scenes: `tools/debug/scenes.py`; shots in `work/qa/warp/`; never ask the user to play to a scene)
- Release:  `python -X utf8 tools/release.py` (patch + verify; never publish without the user; not written yet: phase 9)
- Clean:    `python -X utf8 tools/clean.py` (published projects: lists rebuildable/downloadable files; `--yes` deletes)
- Unpack for RE: `python -X utf8 tools/pgd.py x work/iso/PSP_GAME/INSDIR/DATA.DNS work/re/data.bin`, `python -X utf8 tools/itoc.py x work/re/data.bin work/re/files`

## Paths
- Original ROM: `rom/Gloria Union (Japan).iso` (gitignored; SHA-1 in `rom.sha1`, checked by `tools/check_rom.py`). Emulator: PPSSPPHeadless QA fork (`fetch_emu.py ppsspp-headless`, qa-1, one install per machine in `%LOCALAPPDATA%\translate-retro-game\ppsspp-headless\`); windowed PPSSPP v1.20.4 in `tools/ppsspp/` (github.com/hrydgard/ppsspp/releases, gitignored) for the EBOOT dump and for people. Savestates: `work/states/`.
- Text: `script/` (JSON, phase 4). Tables: `tbl/` (Shift-JIS: no table needed for extract). Glossary: `glossary.md`. RE notes index: `docs/re/README.md`. Fonts and their licences: `docs/fonts.md`.

## Rulings
- Edit source files (.py .lua .asm .tbl .json) only with the file-edit tool; scripts here read and analyse, never `.replace()` and write back.
- Subagents: dispatch the `.claude/agents/` types (translator, reviewer, visual-qa, playtester), never general-purpose: their short tool list cuts each agent's start-up context from ~43k to ~9k tokens. Orca workers: no subagents unless the task asks; do reviews yourself in a fresh read-only pass or with `codex exec`.
- The user's decisions, with the options and reasons: `docs/decisions.md`. Read it before asking the user anything; add each new ruling there the same session.
- Player bug reports: GitHub issues (`gh issue list --label bug`). Copy the attached save into `work/states/`, reproduce in the emulator, fix, commit with `Fixes #N`, and update `docs/status.md`.
- PGD `DATA.DNS` is installable: the game prefers `ms0:/PSP/SAVEDATA/ULJM05813GloriaUnion.Ins/DATA.DNS`. A player's old install overrides the patched disc; the README must say to delete it.
- Japanese-style buttons: circle = OK, cross = cancel. No shipped KIRK key beyond the four in `tools/pgd.py`.

## Status
`docs/status.md`: done, next, open bugs. Update it at the end of every session.
