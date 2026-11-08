# Decisions

The user's rulings on scope, style and trade-offs, newest last. Read before asking the user anything; if a later
decision replaces one, mark the old one "replaced by D<n>" instead of deleting it. Binding term spellings live in
`glossary.md`; this file holds the why.

| # | Date | Question | Options offered | Decision and reason |
|---|---|---|---|---|
| D1 | 2026-11-07 | Honorifics and name order | keep (-san), drop; JP or Western order | Keep honorifics; Western order (given name first). Owner's project-wide answer. |
| D2 | 2026-11-07 | Romanization source for names | official art, earlier patch, Hepburn | Official English names where they exist, else an earlier fan patch, else Hepburn without macrons. |
| D3 | 2026-11-07 | Credits | stay Japanese, translate | English. |
| D4 | 2026-11-07 | Abbreviations | engine work first (default), abbreviate | Default: engine work first; not asked separately. |
| D5 | 2026-11-07 | Graphics text left in Japanese | none (default), list | Translate all of it (titles, menus, banners, cards); keep the original Japanese logo only if it has no official English version. |
| D6 | 2026-11-07 | Specs and plans | need approval, pre-approved | Pre-approved: keep going through every checkpoint. |
| D7 | 2026-11-07 | Existing saves or states | provided, none | None provided; build the debug tool as usual. |
| D8 | 2026-11-07 | Publishing | | Never run `gh release create`, never change repo visibility. The run ends at a built, verified release zip. |
| D9 | 2026-11-08 | Dialogue box capacity (default under D4, not asked) | 3 lines x 288 px at cap 12 (~105 chars); 4 lines at a 16 px pitch with cap-10 glyphs (~170 chars); abbreviate | 4 lines, smaller glyphs: many 3-line Japanese lines need 110-130 English characters, and D4 puts engine work before cutting. Say if the larger 3-line text is preferred. |
| D10 | 2026-11-08 | Register and sound effects (default under D6, not asked) | formal, casual; romanised or English SFX | Casual modern English, light swearing where the Japanese is rough; noises spelt as English sounds. Pre-approved run: say if a different register is wanted. |
| D11 | 2026-11-08 | Item names over the 134 px item-name field (default under D4) | engine work (smaller font), rephrase, abbreviate | Rephrased without abbreviations ("Sea King Shard", "Sage's Stone"); 40 of 246 needed it. A smaller item font would allow the longer forms: phase 7 can revisit. |
