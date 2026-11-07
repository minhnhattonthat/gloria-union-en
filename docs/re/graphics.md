# Graphics and fonts

## Texture format (verified: `tools/ptx.py` renders portraits, cards, fonts and the map correctly)

`PTX@`: CLUT4 or CLUT8, 8888 palette, mostly swizzled. Header in `tools/ptx.py`. Embedded in PTP (packs), PTG@ (sprite sets), PTA (animations), FCT, FPD: `ptx.scan()` finds them by magic. Re-encoding keeps the size, so a replacement that fits the same palette and dimensions changes no offsets.

- **Split textures** (verified: `tests/test_ptx.py`, stacked render of id 2): palette offset 0 means the piece shares the previous piece's palette; `scan()` resolves it. A palette offset of 0 with no earlier piece means the palette is outside the PTX (PTA): `decode()` falls back to a grey ramp.
- **PTG@** (verified: `ptx.ptg()`, names in id 3 and cut-ins read correctly): +4 vertex offset, +8 PTX block offset, +C block size (0 = one PTX at the offset, length unrecorded), +10 u16 w, h. The PTX pieces stack vertically into one atlas; the vertices are GE sprite pairs (top-left, bottom-right) of u16 u, v, x, y, z. The image is cut into 8-line bands, trimmed of transparency, and packed, so raw PTX pieces look like thin noise strips. **Editing a PTG means re-packing bands and rewriting the vertex list**, or keeping the vertices and drawing inside the existing runs.
- **Known defect:** the last rows of many composites show junk (e.g. `Ready Steady Go!` id 131, `Are you ready?`). Guess: the atlas is not a plain vertical stack when the last piece is narrower, or the final vertices are a second layer. Harmless for the survey (text stays readable); fix before writing PTGs (phase 5).
- **PTA** ids 163-211, 1421-1469 and tiles between the bust sets (guess: bust and sprite animation, since each bust set has one beside it): same 8-line band packing, palette outside the PTX, vertex tables not decoded, so these render as grey noise. Whether they hold text is unknown until the tour.

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

## Graphics-text survey: static sweep done

`python -X utf8 tools/survey.py work/re/survey`: 3073 images in 64 sheets, `index.tsv` maps sheet position to id+offset. The script prints what it drops: 729 duplicates, 602 PTG frames (same-size animation runs, 1 in 6 kept). Sides over 300 px are drawn at 1/2.

**How far it was read** (codex was over its limit, so one reader, no independent second pass): full size, sheets 0, 4-6, 13, 35-41, 49-52, 54-57, 63; sheets 1-3 full size only before PTG compositing was added (same id 3 content, names then cut in half); every other sheet at quarter or half scale only, which shows the kind of content but cannot read small text. At that scale 14-17 are cut-ins like 13, 19-31 are 256x272 character busts, 42-48 are map art and stage titles like 41, 53 and 58-62 are cards and character art; nothing broke the pattern. Offsets below are as read off the sheet labels at sheet scale: confirm each against `index.tsv` before using it.

**Not images:** VPD 2083-2361 are voice packs (u32 count, then id/offset pairs of ADX), not PTX; 64 FCT files 2420-2637 are ADX banks; FCT 0 is sound. The opening PMF (h264, 480x272, 64 s, sampled every 3 s) has no text in any frame.

Volume is the main finding: most Japanese is in graphics, not in a font. Rows marked **body** are running story text as images: extract the wording by reading the image; there is no string to pull.

| Where | Element | Japanese? | Size / kind |
|---|---|---|---|
| id 3 +17b580.. +1975d0.. | unit and team names, large and small (イシュト, ピンガー, 海賊, 民兵...): 100+ PTGs in two sizes, plus class names already English at +1a3c10.. | yes | PTG, runs |
| id 3 +131ad0 | 中断データ, ※まだ行動できます!, グロリア海賊団 | yes | PTX |
| id 3 +1583a0 | terrain sheet: 街道 草原 荒野 森林 砂漠 毒沼 海 氷上 水辺 集落 都市 城砦 浜辺 街路 遺跡 路地; 晴れ 雨 霧 雪 雷; 架橋; 昼間 夕方 夜 (+15e1a0) | yes | PTX |
| id 3 +3e8e70 | terrain and object glyphs, weapon kanji 剣 槍 斧 銃 杖 塊 鎌 琴 | yes | PTX |
| id 3 +161060 | 勝利条件, 敗北条件 headers | yes | PTX |
| id 3 +168be0, +398650 | フィールドマップ確認中, ステータス確認中 | yes | PTX |
| id 3 +16db60, +1712c0 | map menu: ターン終了 全体マップ ユニットリスト 地形一覧 カードリスト 中断セーブ 武器タイプ一覧 勝敗条件 オブジェクト一覧 チュートリアル (normal + hilite pages) | yes | PTX |
| id 3 +175400 | ユニット配置, ロケーション | yes | PTX |
| id 3 +33cb90 | 生存ユニット 能力差 ボーナス 地形効果 部隊士気 | yes | PTX |
| id 3 +354640 | skill name list, 2 columns (メイクドール...) | yes; strings too? check | PTX |
| id 3 +3812e0 | アイテムを持っていません, ステータス, アイテム詳細, を装備しました!, 船に装備可能, 詳細を閉じる | yes | PTX |
| id 3 +38bd80, +395d90 | English mostly; 固定, 確認 chips | partly | PTX |
| id 3 +3e2af0, +398650 | 非戦闘ユニットです, 士気, 装備, 勝率, 耐久値, 船内 | yes | PTX |
| id 3 +400c40, +401e20, +4040d0 | legend panels: 味方/敵ユニット; 得意 普通 苦手 移動不可 通行のみ可 戻る; 有利 互角 不利 | yes | PTG |
| id 3 +36f4c0, +3708a0, +3924e0 | 戦闘準備OK?, ターン終了OK?, タクティクスカード選択 | yes | PTG |
| id 3 +4a6960, +4abf60, +4b1840 | 士気ダメージ, Atk.アップ!, Luk.ダウン... (status popups; set not fully listed) | yes | PTG |
| id 3 +3f9a20, +44e910 | 雪道 label on a terrain chip, large and small | yes | PTG |
| id 3 +4444d0, +4494f0 | Save the record of voyage: はい いいえ; ここまでの航海の記録をセーブしますか?; ソフトリセット dialog | yes | PTX |
| id 3 +0xF0390, +0xE0000, +0xEC350, +0xEAED0 | button labels (決定 戻る データ ヘルプ キャラ変更 敵のカード 切り替え 選択 カーソル移動 ...), 枚, 残りカード, 耐久 士気 Lv, 出撃可能, 選択可能 | yes | PTX |
| id 4 +60910, +64ba0 | option text: Battle Setting NORMAL (通常設定) HARD (荒波設定), バトルの難易度を設定してください, option descriptions | yes | PTX |
| ids 26-65 | 200-px red banners: イシュト海賊団進撃! and 39 more team variants | yes | PTX/PTG |
| ids 122-159 | stage clear titles: **all English** (`Repulsed An Enemy`...), several with odd grammar | no | PTG |
| ids 296-~400 | skill cut-ins, card (256x272) then text (288x230): English motto + big English name + kana + `<title><name>` line (`メイクドール / 傀儡師エクシール`) | yes, 2 lines each | about 50 pairs |
| ids ~1047-1362 | character busts, 256x272, no text in the sheets viewed | no | |
| ids 1534-1580 | intro name plates: English (ISHUT...), sometimes with a second smaller line at the bottom of the plate | check | PTG |
| id 1581 +6fd10 | RESULT, すでに最高レベルに達しています, EXPが加算されないユニットです | yes | PTX |
| ids 1582-1588 | chapter cards 1-7: art + Japanese title (始まりの海...) + CHAPTER n | yes | PTG? 480x272 |
| ids 1589-1635 | **body**: stage intro pages, 40+ white-on-black paragraphs, plus team arrow graphics with `-グロリア海賊団-` subtitles and character tags | yes | PTX |
| ids 1636-1639 | **body**: ending/epilogue pages | yes | PTX |
| id 1651 +1b760..+82ed0 | **body**: ending letters, 30 blue lines; `fin` English | yes | PTX |
| id 1703 +2add0, +2c070, +2fb50 | フィールド上にオブジェクトは何もありません, object list and big names 砲台 都市 集落 架橋 城砦 門(開) 門(閉) 投石器 目標地点 柵 アイテム 船 | yes | PTX |
| id 1704 +100, +1b200, +25c60, +46a00, +65f10, +6fb90, +76c30, +79cd0 | アイテム入手, 海賊団勝利, カード入手, ガーロット隊勝利 etc.; 確認 strings; MVP なし; name lists; skill lists; グロリア イシュト海賊団勝利! | yes | PTX |
| id 1757 +fc0 | skill name list | yes | PTX |
| id 1758 +16b0, +3310 | リトライするタイトル画面に戻る, ゲームオーバー | yes | PTX |
| ids 1850-1905 | stage titles, each horizontal (+30) and vertical (+2d90): ハジマリの青 海と空と君と, 黒い牙, 大海の覇者... up to 55 pairs (count not taken) | yes | PTX |
| ids 1945-1991 | event banners: big kanji word + English subline (増援 / Help has arrived.) about 47; +5c40 or +8940 is the kanji | yes | PTX |
| id 1992 +1640.. | credits, 8 pages; D3 says English | yes | PTX |
| id 2020 +20, +1580 | ゲーム再開OK?, ゲーム中断OK? | yes | PTX |
| id 2021 +50 | character profile labels (kana names + `Garlot is...`, weapon types) | yes | PTX |
| id 2022 +58a60 | **body**: prologue page | yes | PTX |
| id 2023 +d0..+11b660 | tutorial plates: 25 titled panels with Japanese callouts | yes | PTX |
| id 2362 +100, +9040 | card effect table (■威力=...), スキル効果と発動タイプ使用条件 | yes | PTX |
| id 2418 +229f0, +28770, +266d0, +2dbd0, +1cfc0, +1dd40, +1f750, +15590 | equipment/ship menus: captain name list, 改造する箇所を選択してください, このアイテムを報酬にしますか?, 並び替え, 装備選択 士気回復 船長選択 改造・修理, 修理 | yes | PTX/PTG |
| id 2419 +59b0, +f380, +24570 | skill name lists, 使用条件 | yes | PTX |
| id 2422 +20 | このアイテムを装備しますか? | yes | PTX |
| id 2424 ~+23a60 | status list with 夜間も砲撃可, 砲撃後も移動可 | partly | PTX |
| id 2426 +3520, 2427 +ecc0 | 残された戦略は..., あと枚, このシナリオでよろしいですか? | yes | PTX |
| id 2427 +80..+15070 | scenario select: difficulty, island names (ルネスト島...), 魔海都市シャンティエ, 15 place plates | yes | PTX/PTG |
| id 2430 +52bd0..+7e3d0 | item conditions: 40 lines (・ガーロット専用, ○グリアライダーに強い...) | yes | PTX |
| id 2430 +8bc50..+9e690 | story scene titles ~ 〜天意の名の下に〜 ~, 18 | yes | PTX |
| id 2430 +28f00, +2aed0, +2e7d0, +30b10, +37bf0 | EXTRA menu: gallery labels, names, CONTENTS, グロリア新海記 | yes | PTX |
| id 2432 +49400..+5d130 | music titles ♪ 怒れる炎..., 12 | yes | PTX |
| id 2362 +bae0..+3da70 | skill names, English only | no | PTG |
| title (id 4 +58ec0, +277170 in id 3) | GAME START... English; `Gloria Union` logo English | no | PTX |
| ICON0, PIC1, INSDIR/ICON0 | English logo, INSTALL DATA | no | PNG |
| ids 1926-1944 | 19 PNGs: team-crest + bust, no text | no | PNG |
| ids 2639-2665 | sepia CGs, no text | no | PTP |
| PMF opening | no burned-in text | no | h264 |

**Still to prove with the tour** (phase 2 debug tool, phase 8): PTA strips contain no text; id 3 small popups are complete; which `+` offsets are drawn from the font rather than from these images (several lists also exist as strings: compare with `script/` in phase 4 before redrawing any).

**Cost note for phase 5:** ids 1589-1639, 1651, 2022 are full pages of story text with no string behind them. Redraw needs a generated page per paragraph (`gen_gfx.py`, `typeset.py`, the skill's `references/graphics.md`), with the wording from a reader transcribing the image. Cut-in kana lines appear on about 50 textures. PTG band packing means a redraw needs a band packer (`ptx.ptg` is the inverse to write).
