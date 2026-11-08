# Polish pass

Minor review findings, deferred (references/translation.md §Review). Tick each `[x]` when fixed or `waived: reason`; the release script refuses to run while any line is unticked.

- [ ] spelling: respell British forms in dialogue to US (D12): colour, defence, favour(ite), honour(ed), rumour, harbour, armour, organisation, travelling, centre, apologise, realised, burnt, savour, flavour, fibre, neighbourhood, analyses, defenceless (`grep -ohiE` over the script's "en" fields)
- [ ] c2:069d6 - Yggdra 戦利品を売って弾代に shipped "sell these spoils and use it for bullet money": "use them" (or "sell the spoils and put it toward bullets")
- [ ] c8:15b89 / c8:1aa68 - 空しい shipped "...How pointless." (Elisha, milk to grow her chest) and "How empty." (Kamuru): "...Who am I kidding." / "How sad is that."
- [ ] e:1edc5c - %2d戦%2d勝 (15-byte buffer) shipped as "%2d fought %2dW": "W" is an abbreviation (D4 flag); a wider buffer (tbl/fmtbuf.tsv) would allow "won". Phase 7 didn't try it (review Minor 6): move the sprintf target (sp+0x130) to a blob buffer or grow the stack frame
- [ ] b020 card quotes e:2872ec-e:287e78 - attribution left-aligned (JP right-aligns it); check in the EXTRA card panel in phase 8
- [ ] s2033:010c8t/010e8t/0113at - team name シャルル海賊団 (JP typo for シャルム) shipped "Charles Pirates": use "Charme Pirates" (team names are dead text: op 0x74)
- [ ] s2068:02b02 - Zazarland 罪人でもなかっただろうに shipped "And I bet they weren't even a criminal": "And I bet whoever wore 'em wasn't even a criminal."
- [ ] s2077:01174 - Elisha 正論、ね shipped "...She's right, isn't she." (Pinger spoke last, but the argument is Zazarland's): "...Makes sense, I guess."
- [ ] s2039:00424 - Blackmore's 機械人形 at Ruru shipped "A wind-up doll": "machine doll" keeps the hint that he knows what she is
- [ ] e:25df84 - scenario title 黒の終止符 shipped "The Black Full Stop" ("full stop" is British, D12): "The Black Curtain Call" or "Black Finale" (check its byte limit)
- [ ] s2034:0096c - 船長を"もの"扱い: "Calling your captain a 'what'" reads oddly; "So your captain's a 'what' now? Poor guy, nobody loves him." or make Elisha's line say "what's mine"
- [x] HUD enemy panel (right, right-aligned): the name has ~68 px before the gauge pips, the player panel 72 (work/qa/hud2_r.png). Fixed after the phase 7 review: HUD budget 68 px (`boxes.py` 4/20/12/10), the 19 names over it rephrased (Mystery Lady, Glaring Man, Bassofondan, Empire Knight, Chantier Blade...).
- [ ] Unit abilities (e:2552b8-e:2561ec) rephrased to one line of 145 px (they show in the 1-row VS skill tag): check terse ones read well in context: 'Strong Attack+' / 'Strong Attacks: up' / 'Strong Attack: lots', 'Weak save lightning', 'No Back-to-Back', 'Card Encyclopedia' (= unlocks it). Review after phase 7 fixed 'Weak but to dark' -> 'Weak save dark', 'Good in Swamp' -> 'Likes Poison Swamp'.
- [ ] e:2554c8 / e:2555c4 - ネクロマンサーに強い/弱い shipped "Strong vs Necros" / "Weak vs Necros": abbreviation (D4 flag; "Necromancers" doesn't fit 145 px in any phrasing tried). Engine fix: a condensed font 2 style (as D15) for the VS skill tag / Notice rows, or measure the real edge (the window is unmeasured, budget 145 is a guess at the screen edge ~150).
- [ ] Leading/trailing blanks (phase 7 review Minor 4): JP pads dropped in e:253a84, e:253ae4, e:253b40, e:253ba0 (centred －…－ save-dialog headers now flush left), e:254094 "0%" (right-aligned), e:258bf0, e:2896cc "%s". Check each on screen in phase 8; restore the pad (spaces or pixel centring) where the layout breaks, else waive. The lint has no blank rule yet.
- [ ] Team names (op 0x74, `at`): 73 English names are cut to the byte limit by insert.py (e.g. s2035:00917t "Black Fang" -> "Black "); harmless while the handler is dead (docs/re/text.md). Confirm dead with a RAM watch on the per-side struct in phase 8; if live, fit each to `max`. Until then script/ English for these differs from the build (phase 7 review Minor 5).
- [ ] D11 item names: phase 7 did not revisit the smaller item-name font (phase 7 review Minor 7). Try a condensed font 2 style (`vwf.STYLE[2]['sx']`, as D15 did for font 4) and restore the 40 long forms if legible; else record "kept, because ..." in D11.
