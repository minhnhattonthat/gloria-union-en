# Gloria Union English translation

Unofficial English fan translation of **Gloria Union** (PSP, Atlus / Sting, 2011, Japan only, ULJM-05813): the
source text and tools that build the patch.

**Just want to play?** Download the patch from [Releases](../../releases) and follow its README. This repository holds
no game data you can play; you need your own dump of the Japanese game.

**Already installed the Japanese game?** Delete `ms0:/PSP/SAVEDATA/ULJM05813GloriaUnion.Ins/` (in PPSSPP:
`memstick/PSP/SAVEDATA/ULJM05813GloriaUnion.Ins/`) before playing: the game prefers that installed copy over the disc,
so an old install shows Japanese text. Save files are separate and are kept.

**Found a bug?** [Report it](../../issues/new/choose): untranslated text, typos, overflow, crashes. Attaching a savestate
helps most.

## Translation status

| Part | Status |
|---|---|
| Story dialogue, battle talk, chants and barks | Translated |
| Menus, items, skills, cards, units, system and save messages | Translated |
| Text drawn as graphics: chapter cards, stage titles, story pages, ending letters, tutorials, banners, buttons, skill cut-ins, scenario select, EXTRA pages | Translated |
| Credits roll | Translated (staff name readings are best guesses) |
| Voice acting | Left in Japanese (audio) |
| English already in the game's art (e.g. big skill names on cut-ins) | Kept as drawn |
| PSP system save dialog | Follows the console/emulator language |
| Leftover developer menu | Left in Japanese (no route to it in the game) |

Known issues: a few abbreviations where a box has no room ("Dur."/"Mor." on the character list, "Dragon" for Dragon
Rider, "vs Necros", "W" for wins in the battle record); some long names on small plates are squeezed. Details and
reasons: `docs/polish.md`, `docs/decisions.md`; open reports: [Issues](../../issues).

Tested in PPSSPP v1.20.4. The EBOOT ships decrypted (runs on PPSSPP and custom firmware); not tested on real hardware.
Cold-boot the patched game: savestates from the Japanese game or an older patch carry the old code and text.

## What's here

| Path | What it is |
|---|---|
| `script/` | Every text block: original Japanese and English. Translation fixes go here. |
| `gfx/` | Redrawn graphics text (`text.tsv`, `pages.tsv`, `cutins.tsv` and the generated PNGs). |
| `glossary.md` | Binding names, terms and style rules. |
| `tools/` | Python build chain: extract, insert, VWF, graphics, lint, release. |
| `tests/` | pytest suite (ROM-dependent tests skip when the ROM is absent). |
| `docs/re/` | Reverse-engineering notes. |
| `docs/decisions.md`, `docs/status.md` | Rulings with their reasons; current progress and open bugs. |
| `docs/fonts.md` | Fonts used and their licences (M PLUS Rounded 1c and Liberation, both OFL 1.1). |
| `AGENTS.md` | Instructions for coding agents (`CLAUDE.md` points to it). |
| `.claude/agents/` | Subagent types (translator, reviewer, visual QA, playtester) with only the tools each needs. |

## Build your own patched ISO

Needs Python 3.12+ and your own dump of the Japanese game.

```sh
git clone https://github.com/minhnhattonthat/gloria-union-en
cd gloria-union-en
# copy your dump to: rom/Gloria Union (Japan).iso
#   (Redump "Gloria Union (Japan)": 551,157,760 bytes, CRC32 5456ec0c, MD5 f97f03879e493f5f48876b5b9babcb60,
#    SHA-1 5f63c8e9751bd109671ee1f5a42cdfb94487cddb; the build refuses any other dump, see rom.sha1)
python -X utf8 build.py                                # -> build/gloria_en.iso
python -X utf8 tools/check.py                          # tests + text lint
python -X utf8 tools/release.py                        # gates + xdelta3 patch + zip in release/
```

## Support

If you enjoy this translation, you can support my work on Ko-fi:

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/minhnhattonthat)

## Licence

Tools and English translation: MIT. The original Japanese text in `script/` is Atlus / Sting's and is included only so
the translation can be checked against it. Gloria Union is (c) Atlus / Sting; this project is not affiliated with
them. Do not share patched ISOs.

The translation was made with extensive AI assistance (Claude by Anthropic). Corrections are very welcome.
