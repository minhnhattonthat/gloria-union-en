# Gotchas for the skill

One line per gotcha: the reference file it belongs in, then the fact.

- references/platform-psp.md: PGD (`\0PGD`, e.g. `INSDIR/DATA.DNS`) is not a blocker: with drm_type 1 the vkey comes from the MAC at 0x70 (amctrl `bbmac_getkey`), so no game key is needed. `tools/pgd.py` here is a ~100-line Python port; worth promoting.
- references/platform-psp.md: `cpk.py` handles only TOC CPKs; ITOC-only CPKs (no names) need id-order walking with Align padding, see `tools/itoc.py`; `unlayla` there decompresses CRILAYLA. `Entry.parse` returns nothing and `list` prints nothing on these rather than failing.
- references/setup.md: `fetch_emu.py` fails with `CERTIFICATE_VERIFY_FAILED` on stock Python for Windows; `SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())")` fixes it. A folder already installed makes it exit with "not empty", which reads like a failure but is fine.
- SKILL.md: `pre-commit` setup says to edit `CHECK=`; `sed -i` is blocked by the guard and a heredoc that writes source is too, so use the edit tool as stated. Inline `python - <<'E'` with backslash escapes is also blocked: write a scratch script.
- SKILL.md §Tools: a `strings` binary is not on Git Bash for Windows; use Python regex.
- references/graphics.md §Survey: dedupe on whole pixels: a first-256-bytes hash collapsed every texture with a blank top, and thin noise strips can be band-packed atlases (GE sprite vertices u, v, x, y, z in pairs) that must be composited before text is readable. Survey sheets at 1:1: 120-px thumbnails of 512-px atlases hide text.
- references/emulator-qa.md §Visual QA: `codex exec -i` is the fallback reviewer for Orca workers but can be over quota; sheets read in the main thread cost about 3k tokens each, so triage by id range and overview mosaics first.
