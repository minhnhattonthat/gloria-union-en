# Reverse-engineering notes

One file per subsystem (text engine, pointers, compression, font, graphics). Mark every finding with how far it is
proven, so a later session doesn't build on a guess:

- **verified** - and how: a decoded known string, a corrupt-and-boot test, a breakpoint hit on the drawing path, a
  passing roundtrip test. Name the test or savestate.
- **guess** - and why it seems likely (byte pattern, another game, an earlier patch's notes). Promote it to verified
  before code depends on it.

Addresses are for the dump in `rom.sha1` unless a note says otherwise.

| File | Covers | State |
|---|---|---|
| disc-and-containers.md | ISO, EBOOT layout, PGD, CPK, file map by id | verified; PGD and CPK rebuild not written yet |
| text.md | encoding, script records and references, common text, EBOOT strings, free space | script format verified; EBOOT slots and common-text tables partly guessed |
| graphics.md | PTX, PTG, fonts, graphics-text survey | PTX and PTG read verified; PTA undecoded; PTG last-row defect open; static sweep done, tour pending |
