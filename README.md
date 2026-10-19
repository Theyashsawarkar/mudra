# mudra

**mudra** (मुद्रा, "gesture") — Keybinding search. A tool for [Vyom](https://github.com/Theyashsawarkar/vyom), the keyboard-driven panels of [Vayu](https://github.com/Theyashsawarkar/vayu); in Vayu it replaces keybind-search.py's wofi popup.

> Search every keybinding (sway, tmux, kitty, zed, rmpc, tools...) by what it does; real key caps; Enter runs it.

## Features

- Every keybinding **by what it does** ("kill window", "volume"), with real **key caps** and chords (`Ctrl A then &`).
- Grouped by app, with a tab per app (sway, tmux, kitty, zed, rmpc, Vyom…).
- `Enter` **runs the binding**: sway ones through swaymsg, tmux ones replayed into your most recent tmux client; anything else copies its keys.
- Bindings come from a command printing JSON (Vayu's `keybind-search.py --json`); without one it reads sway's own config.

## Keys

| Key | Action |
|---|---|
| `Enter` | Run the selected keybinding (sway and tmux), else copy its keys |
| `Ctrl+C` | Copy the selected keybinding's keys |
| `Ctrl+1..9` | Show all, or one app's keybindings |
| `Esc` | close |

Every Vyom panel also has: `Up`/`Down` (or `Ctrl+K`/`Ctrl+J`) to move, `Page Up`/`Page Down`, `Tab` to switch to the next tool.

## Requirements

- [Vyom](https://github.com/Theyashsawarkar/vyom) 0.2 or newer (Python 3.11+, GTK 4, gtk4-layer-shell, a layer-shell compositor)
- optional: swaymsg, tmux (running bindings)

## Install

```sh
git clone https://github.com/Theyashsawarkar/mudra ~/.local/share/vyom/plugins/mudra
vyom reload        # or log out and in
vyom mudra         # open it (again: close it)
```

Bind it to a key, e.g. in sway:

```
bindsym $mod+<key> exec vyom mudra
```

Update: `git -C ~/.local/share/vyom/plugins/mudra pull && vyom reload`. `vyom list` shows every installed tool and why one would be skipped.

## Configuration

In `~/.config/vyom/config.toml` (all optional):

```toml
[plugin.mudra]
# source_command: command printing the bindings as JSON (default: keybind-search.py --json (if installed))
```

## License

MIT.
