# Fonts

Every font or glyph sheet the build reads ends up inside the released patch, so its licence must allow that. One row
per file; a font with no known licence doesn't go into a release.

| File | Source (URL, version) | Licence | Redistributable in a patch | Used for | Changes made |
|---|---|---|---|---|---|
| `fonts/MPLUSRounded1c-ExtraBold.ttf` | github.com/google/fonts `ofl/mplusrounded1c` (main, fetched 2026-11-08); licence text `fonts/OFL-MPLUSRounded1c.txt` | OFL 1.1 | yes, as rendered glyphs (the TTF itself is not in the patch) | `tools/vwf.py`: ASCII 0x20-0x7F for engine fonts 1-3 (dialogue 20 px, small 14x16, name tags 24 px italic) | rendered at a cap height matching each game font, 1 px black outline, game palettes; font 3 sheared 0.2 for italic |
| `fonts/LiberationSerif-Bold.ttf`, `LiberationSans-Bold.ttf`, `LiberationSans-BoldItalic.ttf`, `LiberationSans-Regular.ttf` (added 2026-11-09: small light lettering, options/result; EXTRA card name plates), `LiberationSerif-Regular.ttf` (added 2026-11-09: 2433 serif card name sheet) | github.com/liberationfonts/liberation-fonts release 2.1.5 (`liberation-fonts-ttf-2.1.5.tar.gz`); licence `fonts/OFL-Liberation.txt` | OFL 1.1 | yes, as rendered pixels in redrawn textures | `tools/gfx.py`: chapter card titles and game over (serif bold), small menu labels (sans bold italic) | none; rendered, squeezed (xscale) or slanted per texture, quantized to each texture's palette |
