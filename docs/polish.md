# Polish pass

Minor review findings, deferred (references/translation.md §Review). Tick each `[x]` when fixed or `waived: reason`; the release script refuses to run while any line is unticked.

- [ ] spelling: respell British forms in dialogue to US (D12): colour, defence, favour(ite), honour(ed), rumour, harbour, armour, organisation, travelling, centre, apologise, realised, burnt, savour (`grep -ohiE` over the script's "en" fields)
- [ ] e:1edc5c - %2d戦%2d勝 (15-byte buffer) shipped as "%2d fought %2dW": "W" is an abbreviation (D4 flag); a wider buffer (tbl/fmtbuf.tsv) would allow "won"
- [ ] b020 card quotes e:2872ec-e:287e78 - attribution left-aligned (JP right-aligns it); check in the EXTRA card panel in phase 8
- [ ] s2033:010c8t/010e8t/0113at - team name シャルル海賊団 (JP typo for シャルム) shipped "Charles Pirates": use "Charme Pirates" (team names are dead text: op 0x74)
- [ ] s2068:02b02 - Zazarland 罪人でもなかっただろうに shipped "And I bet they weren't even a criminal": "And I bet whoever wore 'em wasn't even a criminal."
- [ ] s2077:01174 - Elisha 正論、ね shipped "...She's right, isn't she." (Pinger spoke last, but the argument is Zazarland's): "...Makes sense, I guess."
- [ ] s2039:00424 - Blackmore's 機械人形 at Ruru shipped "A wind-up doll": "machine doll" keeps the hint that he knows what she is
- [ ] s2034:0096c - 船長を"もの"扱い: "Calling your captain a 'what'" reads oddly; "So your captain's a 'what' now? Poor guy, nobody loves him." or make Elisha's line say "what's mine"
