# Text windows and width budgets

Data: `tools/boxes.py` (`BUDGETS`, `GROUPS`, `SOURCE`), `tbl/boxes.tsv` (entry -> window classes seen on tours),
`tbl/fmtbuf.tsv` (byte limits of sprintf'd strings, enforced by `insert.py`). `boxes.budget(entry)` gives
`(px per line, lines, class, measured?)` for every entry to translate (`tests/test_boxes.py`).

## Classes

A class is `font/original columns/cell pitch/rows` of the writer's window. Each of the 42 classes seen on the marker
and fit tours has a budget in `BUDGETS` with the shot it was read from (38 measured, 4 tagged guess, one entry
each: `1/15/20/3` item drop window, never on screen; `1/18/20/1` "this scenario?" text, never drawn: the screen
shows a PTX instead; `2/10/14/1` card skill name drawn faded behind the art; `2/4/14/1` Factor RESULT value).
A line also stops at `boxes.cell_cap(k)` characters (3 x original columns). An entry seen in several classes takes
the smallest budget. Story and common text: dialogue `1/16/18/4` (288 px x 4).

How to measure one: fill an entry to its width (`stress.py`, `build.py --qa ID=TEXT`), reach the screen
(`warp.py SCENE --text-log --state-at TEXT F` saves a state when the text first draws; `step.py F "wait 60" --each`),
read where the frame, the next field or the screen edge cuts the line. Box widths in the logs are cells x pitch, not
frames.

## Entries never seen on a tour (10,088 EBOOT entries, all `measured? = False`)

1. **Same pointer table as a seen entry** (`table_classes`: `w:` slots no more than 0x40 apart): the table's classes.
   A run stops at a `boxes.SPLITS` address (tables that touch). **Unit records** 0x2EE82C-0x2EF27C (220 x 12 bytes:
   full name, short name or 0, team name or 0; no index aliases in the original) are classed by field
   (`boxes.record_classes`), measured: the battle HUD (`4/20/12/10`, 72 px) draws the short name, else the full name
   (reader 0xF38E4 -> 0x112080; 0x112038 returns the full name); full map unit lists (`4/20/12/6`, 80 px) show team
   names. The 4-byte **place list** after it (0x2EF27C-0x2EF4CC: villages, spots, Treasure Barrel) was seen only in
   the fight screen place bar `1/15/20/1` (e:2816e4), so it takes that 200 px budget. Font 4 is condensed (`sx` 0.8,
   D15). Other splits: skill effects / skill use conditions at 0x2CA150, game storage messages / PSP dialog messages
   at 0x2EDA40.
   `boxes.ROW_OF`: skill effects (0x2CA000-0x2CA14C) draw on line 1 of the card select bottom (`2/22/14/1`, 290 px);
   line 2 is the use condition after its label (`2/22/14/2`, 225 px). `boxes.ROWS_FROM_TEXT`: win/lose condition
   windows take as many rows as the text has lines.
2. **`SOURCE` ranges** (by slot address, what the table holds): battle barks and skill mottos -> bark bubble
   `1/20/20/1`; skill-unusable and morale messages -> battle panel `1/21/20/3`; place names, character catchphrases
   -> `1/30/18/1`; item/card conditions -> `2/15/14/2`; unit class names -> `2/10/14/7`; EXTRA music titles, quotes,
   card conditions -> `2/30/14/25`; stage outcome/recap lines -> `1/30/20/6`; PSP system dialog text (`[0A]` breaks,
   firmware font, wraps itself) -> 400 px x 6.
3. **Other single strings built in code** (`i:` slots): `1/21/20/3`.

Phase 7/8: a guessed entry that comes out long is measured on its screen, not abbreviated. Check the screens of
groups 2 and 3 in the QA tour.

## Known limits outside px

- Byte limits (`tbl/fmtbuf.tsv`): titles 28, item names 35, card effects 57, `%2d戦%2d勝` rows 16...
- Item descriptions: one paragraph, the build wraps them (`insert.desc_breaks`, `DESC_FIT`).
- Treasure bubble (`1/15/20/2`, code 0x10EC80): text at x 285; the bubble grows with the text past the screen edge.
