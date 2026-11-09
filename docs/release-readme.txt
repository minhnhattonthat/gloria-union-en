Gloria Union - English fan translation v{VERSION}
=================================================

Unofficial English patch for Gloria Union (PSP, Atlus / Sting, 2011, Japan only, ULJM-05813).
This zip holds only the patch. You need your own dump of the Japanese disc; no game data is included,
and pre-patched ISOs must not be shared.

What is translated
------------------
- All story dialogue, battle talk, chants and barks.
- Menus, items, skills, cards, unit and status screens, system messages, save/load prompts.
- Text drawn as graphics: chapter cards, stage titles, story pages, ending letters, tutorials,
  banners, buttons, the skill cut-ins, scenario select, EXTRA pages and the credits.
- Left as is: voice acting (Japanese audio), English already in the game's own art (kept with its
  original spelling, e.g. the big skill names on cut-ins), the PSP system save dialog (follows your
  console/emulator language), and a leftover developer menu with no route in the game.

Patching
--------
Base image (Redump "Gloria Union (Japan)", http://redump.org/disc/ ...search ULJM-05813):
  File:  Gloria Union (Japan).iso
  Size:  {BASE_SIZE} bytes
  CRC32: {BASE_CRC32}
  MD5:   {BASE_MD5}
  SHA-1: {BASE_SHA1}

The patch needs an unmodified dump with exactly these hashes.

1. Get xdelta3 (or the GUI "Delta Patcher").
2. Run:  xdelta3 -d -s "Gloria Union (Japan).iso" {PATCH} "Gloria Union (English).iso"
3. Check the result:
  CRC32: {OUT_CRC32}
  SHA-1: {OUT_SHA1}

IMPORTANT: delete the old install data
--------------------------------------
The game installs its data to the memory stick and prefers that copy over the disc. If you ever
installed the Japanese game, delete this folder first, or you will see Japanese text:
  ms0:/PSP/SAVEDATA/ULJM05813GloriaUnion.Ins/
(in PPSSPP: memstick/PSP/SAVEDATA/ULJM05813GloriaUnion.Ins/). Then reinstall from the title screen
if you want the faster loading. Your normal save files are separate and are kept.

Tested on
---------
PPSSPP v1.20.4 (Windows). The EBOOT is shipped decrypted, which PPSSPP and custom firmware run;
it was not tested on real hardware. Start from a cold boot: savestates made with the Japanese game
or an older patch carry the old code and text.

Buttons are Japanese style: Circle = OK, Cross = cancel.

Known issues
------------
- A few labels are abbreviated where the box is too small for the full word: "Dur." / "Mor."
  (Durability / Morale) on the character list and status screen, "Dragon" for Dragon Rider on the
  status move chip, "Strong vs Necros" / "Weak vs Necros" in unit abilities, and "W" for wins in the
  "NN fought NNW" battle record.
- Some long names on small plates (islands on the scenario map, a few scenario titles, terrain
  names on the field bar) are drawn in a squeezed or small font.
- Report bugs at https://github.com/minhnhattonthat/gloria-union-en/issues (a savestate helps).

Credits
-------
Translation, hacking and tools: minhnhattonthat, with extensive AI assistance (Claude by Anthropic);
corrections are very welcome. Official English names follow Atlus USA's Yggdra Union and Blaze Union
where the characters appear there.
Fonts: M PLUS Rounded 1c (SIL Open Font License 1.1), Liberation Sans / Serif (SIL Open Font License 1.1).

Gloria Union is (c) Atlus / Sting. This is an unofficial fan project, not affiliated with them.
