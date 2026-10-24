# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

## v0.3.2 -- 2026-10-24

- drishya's keys (the video player) show with their own colour and icon.

## v0.3.1 -- 2026-10-24

- pramana's keys (the polkit password prompt) show with their own colour
  and a lock icon.

## v0.3.0 -- 2026-10-24

- **Search by keys**: a query that names a modifier (`ctrl+h`, `super q`,
  `alt 1`, `prefix s`) finds the bindings with those keys, exact ones
  first; a capital letter counts as Shift.
- **Every word on its own, in any order**, and the app's name is searchable:
  "tmux kill" finds tmux's kill bindings (it found nothing), "wifi" finds
  Wi-Fi. Words as written rank first; loose matching ("vol" in "quick
  settings") no longer pulls in noise.
- **Ranked, not grouped, while searching**: one list, best match first, the
  app as a badge on each row (grouped by app only with an empty box). The
  best match used to sit in whichever app group came first.
- **Tabs numbered (Vyom 0.4.0), most bindings first**, all of them: the
  app you jump to most gets the low number, and none is left out (it
  stopped at nine apps).
- Key caps in the theme's colours (they were fixed Catppuccin); "or" between
  alternatives (`Ctrl+Tab or Ctrl+Shift+Tab`) instead of a "then" chord.
- Icons and colours for nāda, vesha, vinyasa and anumati bindings.

## v0.2.0 -- 2026-10-24

- App tabs switch like every Vyom tool's tabs (Vyom 0.3.0): `Ctrl+H` / `Ctrl+L` for
  the previous / next app, `Ctrl+1..9` and `Ctrl+0` by number (now up to ten apps,
  was nine). Needs Vyom 0.3.0.

## v0.1.2 -- 2026-10-21

- A website (GitHub Pages, https://theyashsawarkar.github.io/mudra/): the README as a home page, the
  changelog, and architecture decision records (`docs/adr/`), built from these files by
  `scripts/build-site.py`; CI checks the site is up to date.

## v0.1.1 -- 2026-10-21

- Documentation for open source: a logo and banner, a full README (features,
  install, usage, configuration, troubleshooting, the whole Vyom family),
  CONTRIBUTING, SECURITY and CODE_OF_CONDUCT, issue and pull request
  templates, and CI (compiles, checks plugin.toml and that every key is
  documented).

## v0.1.0 -- 2026-10-19

- First release, as its own repository: keybinding search. Replaces keybind-search.py's wofi popup in Vayu.
- Every keybinding **by what it does** ("kill window", "volume"), with real **key caps** and chords (`Ctrl A then &`).
- Grouped by app, with a tab per app (sway, tmux, kitty, zed, rmpc, Vyom…).
- `Enter` **runs the binding**: sway ones through swaymsg, tmux ones replayed into your most recent tmux client; anything else copies its keys.
- Bindings come from a command printing JSON (Vayu's `keybind-search.py --json`); without one it reads sway's own config.
