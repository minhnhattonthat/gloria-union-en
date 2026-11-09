# Visual-QA reviewer brief - Gloria Union (PSP)

You review contact sheets from a translated build's QA tour and give each one a verdict. Read-only on everything
except your one verdict file: no edits to the repo, no git, no subagents. (Orca workers: the implementer does this
itself in a fresh read-only pass, per AGENTS.md.)

## Inputs (in your dispatch)
- A chunk file: one `id<TAB>path` line per sheet. Read every sheet in it; none may be skipped.
- Your verdict file: `work/qa/verdicts/<chunk>.tsv`.
- The original ISO's sheets (`work/qa/tour_jp/`, same ids) and `glossary.md`.
- Each scene folder (`work/qa/tour/<scene>/`) also holds `text.tsv` (every text the writer drew, with its shot
  name) and the full-size shots `t000.png..`, `proof.png`: zoom a full-size shot rather than the sheet.

## How to look
- Read each sheet whole first. Where text is small, zoom into it with
  `python -X utf8 $SKILL/scripts/sheet.py SHOT.png --crop x,y,w,h --zoom 3 --out <scratch>.png` and read that.
- When something looks wrong, open the same id from `tour_jp/` (`sheet.py EN.png --compare JP.png`). If the
  original shows the same thing, it is the game's own behaviour: `ok`, with a note.
- Zoom into every Yes/No prompt, selection box, menu row and speech bubble: a few pixels of misalignment don't show
  at sheet scale. To measure one: `python -X utf8 $SKILL/scripts/inkbox.py SHOT.png x,y,w,h`.

## Judge
An `issue` is any of:
- Japanese still visible;
- text overflowing a box, clipped by a frame, or running off screen;
- text off-centre where the original centres it: an option in its selection box or cursor brackets, a label, a bubble;
- garbage tiles, wrong or missing glyphs, a strike or stray pixels across letters;
- broken line breaks: a word split mid-line, a page ending mid-sentence, a one-word last line;
- an empty box where text belongs;
- a name that differs from `glossary.md`.

Standing non-bugs, `ok`:
- text still typing out, a box mid-fade or mid-scroll, a cursor caught mid-blink;
- a map or scene still loading after a warp; a black or fading frame between scenes;
- anything identical in the original's sheet.
- English already in the game's art with the game's own typos or odd phrasing (SKELTON, `To The Victry`, team-banner
  sublines like "Them heart was broken."): kept by decision (texture-typo default, `docs/status.md` Waiting on the user).
- The skill cut-ins' big English skill names (MAKE DOLL etc.) and blackletter mottos are the game's art (D17).
- The dialogue box shows 4 smaller lines instead of 3 (D9).
- The story pages scroll up through a ~2-line strip at the screen bottom: a page cut at the strip's edge is the game.
- The first scene of every warp is the storage check ("Checking the storage media...").
