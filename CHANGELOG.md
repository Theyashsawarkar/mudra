# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

## v0.1.0 -- 2026-10-19

- First release, as its own repository: keybinding search. Replaces keybind-search.py's wofi popup in Vayu.
- Every keybinding **by what it does** ("kill window", "volume"), with real **key caps** and chords (`Ctrl A then &`).
- Grouped by app, with a tab per app (sway, tmux, kitty, zed, rmpc, Vyom…).
- `Enter` **runs the binding**: sway ones through swaymsg, tmux ones replayed into your most recent tmux client; anything else copies its keys.
- Bindings come from a command printing JSON (Vayu's `keybind-search.py --json`); without one it reads sway's own config.
