# Translator brief - Gloria Union (PSP, Sting/Atlus, 2011)

You translate part of the Japanese script of Gloria Union into English for a fan patch. A light-hearted pirate
fantasy tactics game: Ishut, a loud, good-natured young pirate captain, hunts the legendary crystals with his
long-suffering henchman Pinger and a growing crew of oddballs; the Lukia Empire, rival pirates and an ancient
Euforian power get in the way. Comedy most of the time, sincere when it matters.
Work only on the batches named in your dispatch, one at a time in order, each to a passing check before the next.

## Read first
1. `glossary.md` - binding names and terms, the rulings, and voice notes per character.
2. `docs/synopsis.md` - plot so far and who is who (grows as the story is translated).
3. `build/terms_<batch>.txt` - glossary rows found in the batch when it was split (may be stale: glossary wins).

## Input: `work/tl/<batch>.tsv`
`id<TAB>speaker<TAB>form<TAB>limit<TAB>Japanese`. form: `dlg` (story and tutorial talk), else the EBOOT table it
came from (`names` unit/team names, `items`, `data` stage hints and card text, `ui1-3` menus and help, `messages`,
`saves`/scenario titles, `barks` battle cries, `chants` skill incantations). ` / ` separates the original lines of one
box. limit: `288px x4` = 4 lines of 288 px (the merge wraps one paragraph to it); `?` = the window was never measured
(a warning, not a reason to cut); `NB` = a hard byte limit (sprintf buffer). Each Japanese text appears once in the
whole job, so a short line may be used in several places: keep it neutral when the context is unclear.

## Output: `work/tl/<batch>.out.tsv`, written with your file-write tool (not a shell heredoc)
`id<TAB>English`, every input id once, same order. Plain ASCII: straight quotes, `...`, `--`; no tabs, no Japanese
or fullwidth characters. Dialogue is one paragraph: the merge wraps it; write `\n` only where a break must fall
(a list, a menu row pair). Copy printf codes (`%s %d %2d %02d`) and `[0A]` exactly; never `%dth`.

## Validate
`python -X utf8 tools/batches.py check <batch>` until it prints OK (WARN lines don't fail). Try a long line first
with `python -X utf8 tools/batches.py fit ID "English"`.

## Style
- Faithful: keep the information and order of ideas; adapt idiom, not meaning. Don't add facts or skip any.
  Wordplay: make the joke land in English (no translator notes).
- Keep the speaker audible (voice table in `glossary.md`). JP register markers become English devices: rough
  べらんめぇ speech (ぜ/ねぇ/てめぇ) -> "ya", "ain't", "damn", clipped grammar; polite henchman speech (〜っす/ですよ)
  -> deferential but snarky; feminine わ/かしら/のね -> "I wonder...", "you know", "dear"; robot/katakana speech ->
  stilted capitalised-free English with odd stops. A line any speaker could have said is a mistake.
- Names and terms exactly as in the glossary; full forms, never abbreviate to fit (D4). If it truly cannot fit, keep
  the meaning and report `LONG: id`.
- Honorifics kept and hyphenated after names (Ishut-san, Pamela-sama); 兄貴 (Pinger to Ishut) = "Boss".
  Name order Western.
- Punctuation: 「」 -> "...", 『』 -> '...', …… -> `...`, ！？ -> `!?`, ～ -> stretch the word ("Heeey") or drop.
  Fullwidth stat words (ＴＥＣ, ＧＥＮ ...) use the glossary's English stat names.
- Unit names (`names`) fit 72 px of the 12 px battle font (~11 letters): use the glossary form; report overflow.

## Consistency
Never edit `glossary.md` in a parallel run. For a recurring name or term not in it, pick a form, use it
consistently, and report it.

## Report (reply with only this)
Files written and entry count; then any lines: `NEW TERM: jp -> en`, `UNSURE: id - note`, `LONG: id - note`.
