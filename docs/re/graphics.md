# Graphics and fonts

## Texture format (verified: `tools/ptx.py` renders portraits, cards, fonts and the map correctly)

`PTX@`: CLUT4 or CLUT8, 8888 palette, mostly swizzled. Header in `tools/ptx.py`. Embedded in PTP (packs), PTG@ (sprite sets), PTA (animations), FCT, FPD, VPD: `ptx.scan()` finds them by magic. 5413 textures, 3303+ unique. Re-encoding keeps the size, so a replacement that fits the same palette and dimensions changes no offsets.

## Fonts: id 3, section 1 (nested FCT at 0x52C0) (verified: rendered; index tables read)

| Sub | Offset | What |
|---|---|---|
| 0 | 0x5310 | 128x216 small battle font: kana, A-Z, a-z, digits (PTX). Latin already present |
| 1 | 0x8970 | PTP, 4 pages 512x500/180: font A (white with dark outline), 2096 glyphs. Latin set is partial (`ABCDEGKLMNOPRST...`) |
| 2 | 0x73B10 | index for A: u32 byte count, u16 SJIS codes in glyph order, then u32 bucket starts per lead byte |
| 3 | 0x74BB0 | PTP, 2 pages: font B, about 750 glyphs |
| 4 | 0xAAC90 | index for B |
| 5 | 0xAB2C0 | PTP, 2 pages: font C, small |
| 6 | 0xD73A0 | index for C |

The index holds no widths: glyphs sit in fixed cells, so spacing comes from code. SJIS code to glyph by lookup, so fullwidth Latin (0x8260..) can be redrawn or added; a VWF needs the EBOOT draw routine (phase 5, not found yet; `smlFontWrite` at 0x253774 is a debug path). Each font's Latin coverage is partial, so English needs new glyphs in all three.

## Graphics-text survey: INCOMPLETE

Status: tool done (`python -X utf8 tools/survey.py work/re/survey --sample 6`: 3303 unique textures in 31 sheets of 108, `index.tsv` maps cell to id+offset; drop `--sample` for all, sprites sampled 1 in 6 otherwise). **Sheets not yet read; finish this table in the next session.** Seen so far:

| Where | Element | Japanese? |
|---|---|---|
| id 3 +0xF0390 (240x144) | button labels: 決定, 戻る, データ, ヘルプ, キャラ変更, 敵のカード, 切り替え, 選択, カーソル移動, ステータス, 船長変更, 戻る, フィールド確認, 勝利条件, マップ, カードデータ, 次のページへ, 確認をスキップ, 終了 (some already English: Location, Unit, Data OK, Cancel, Change, Skip) | yes |
| id 3 +0xE0000, +0xEC350, +0xEAED0 | digit strips with `map`, 枚, 残りカード, 耐久 士気 Lv, 出撃可能, 選択可能 | yes (labels) |
| id 297 and similar (288x230) | skill cut-ins: English motto, big English name, kana + kanji line (`メイクドール 傀儡師エクシール`) | yes, kana line |
| title screen | logo English; menu (GAME START + Japanese rows?) | check |
| PMF opening | no burned-in text seen | check |
| ids 1926-1944, id 3 sec 10-12 | PNGs | unread |
| FPD 1652-1702, VPD 2083-2361 | portraits/CGs? | unread |
| ICON0, PIC1 | XMB art | unread |
