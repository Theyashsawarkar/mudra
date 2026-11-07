<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img alt="mudra" src="assets/banner-dark.svg" width="560">
  </picture>
</p>

<!-- identity -->
<p align="center">
  <b>यतो हस्तस्ततो दृष्टिर्यतो दृष्टिस्ततो मनः ।<br>
  यतो मनस्ततो भावो यतो भावस्ततो रसः ॥</b><br>
  <i>Where the hand goes the eyes follow; where the eyes go, the mind; where the mind goes, feeling; and where feeling goes, delight.</i><br>
  <sub>Abhinaya Darpaṇa, c. v. 37</sub>
</p>
<!-- /identity -->

<p align="center">
  <b>Search every keybinding (sway, tmux, kitty, zed, rmpc, tools...) by what it does; real key caps; Enter runs it.</b><br>
  Keybinding search. A tool for <a href="https://github.com/Theyashsawarkar/vyom">Vyom</a>, keyboard-driven panels for Wayland.
</p>

<p align="center">
  <a href="https://github.com/Theyashsawarkar/mudra/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Theyashsawarkar/mudra/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/Theyashsawarkar/mudra/releases"><img alt="Release" src="https://img.shields.io/github/v/release/Theyashsawarkar/mudra?color=cba6f7&label=release"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-f5e0dc"></a>
  <a href="https://github.com/Theyashsawarkar/vyom"><img alt="Vyom 0.6+" src="https://img.shields.io/badge/vyom-0.6%2B-89b4fa"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-a6e3a1">
  <img alt="Wayland" src="https://img.shields.io/badge/wayland-layer--shell-94e2d5">
</p>

<p align="center">
  <img alt="mudra: keybindings panel" src="assets/screenshots/mudra.png" width="100%">
</p>

> *Mudra* (मुद्रा) is Sanskrit for "gesture": a gesture with a meaning, which is what a key binding is.

mudra is keybinding search for [Vyom](https://github.com/Theyashsawarkar/vyom): one keyboard-driven panel that opens instantly, with live data, a preview and a key for everything. It runs on any compositor with the layer-shell protocol (sway, Hyprland, river, niri, Wayfire, labwc…). In [Vayu](https://github.com/Theyashsawarkar/vayu), the desktop it was built for, it replaces keybind-search.py's wofi popup.

## Contents

- [Features](#features)
- [Install](#install)
- [Usage](#usage)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [The Vyom family](#the-vyom-family)
- [Contributing](#contributing)
- [License](#license)

## Features

- Every keybinding **by what it does** ("kill window", "volume"), the words you typed in peach, with real **key caps** at the right and chords joined by a quiet "then" (`Ctrl A then &`), in your theme's colours.
- **Each app is a coloured chip** at the start of its rows (Sway, Tmux, Zed, Vyom…), always the same colour.
- **Clashes stand out**: a key bound twice in the same app and scope gets a red "Clash" chip, and the preview says what else it does.
- **Or by its keys**: type `ctrl+h`, `super q`, `alt 1`, `prefix s` and you get what those keys do, exact matches first.
- **Every word counts, in any order**: "tmux kill", "window kill", "wifi" (finds Wi-Fi).
- While you search, one list ranked by match; with an empty box, grouped by app with a count on each group.
- A **numbered tab per app**, most bindings first, with counts on the biggest (`Sway 106`); the smallest apps share an "Other" tab. `Ctrl+2` is the second, `Tab` the next.
- The preview shows the keys as big caps, **where it's defined** (`~/.config/sway/config:142` for sway, kitty and zed; the file for a tool's own keys) and what it does, with **Run it** (`Enter`) and **Copy keys** (`Ctrl+C`) buttons.
- `Enter` **runs the binding**: sway ones through swaymsg, tmux ones replayed into your most recent tmux client; anything else copies its keys.
- Bindings come from a command printing JSON (Vayu's `keybind-search.py --json`); without one it reads sway's own config.
- Keyboard first: every action has a key, shown in the footer; the mouse works too.
- Never freezes the panel: slow commands run in the background.

## Install

### Requirements

- [Vyom](https://github.com/Theyashsawarkar/vyom) 0.6 or newer (Python 3.11+, PyGObject, GTK 4, [gtk4-layer-shell](https://github.com/wmww/gtk4-layer-shell), a Nerd Font)
- optional: swaymsg, tmux (running bindings)

### Install

```sh
git clone https://github.com/Theyashsawarkar/mudra ~/.local/share/vyom/plugins/mudra
vyom reload           # pick it up (or log out and in)
vyom mudra            # open it; run it again to close
```

Give it a key in your compositor, e.g. sway:

```sh
bindsym $mod+<key> exec vyom mudra
```

### Update and uninstall

```sh
git -C ~/.local/share/vyom/plugins/mudra pull && vyom reload     # update
rm -rf ~/.local/share/vyom/plugins/mudra && vyom reload          # uninstall
```

## Usage

Open it with `vyom mudra` (or your key). Type to search; the footer always shows the keys for what's selected.

| Key | Action |
|---|---|
| `Enter` | Run the selected keybinding (sway and tmux), else copy its keys |
| `Ctrl+C` | Copy the selected keybinding's keys |
| `Esc` | Close the panel |

Every Vyom panel also has `Up`/`Down` (or `Ctrl+K`/`Ctrl+J`) to move and `Page Up`/`Page Down` to jump; its tabs, its main kinds, switch with `Tab`/`Shift+Tab` (or `Ctrl+H`/`Ctrl+L`), or `Ctrl` with the number shown on a tab.

## Configuration

Everything is optional, in `~/.config/vyom/config.toml` under `[plugin.mudra]`:

| Setting | Default | What it does |
|---|---|---|
| `source_command` | keybind-search.py --json (if installed) | Command printing the bindings as JSON |

Run `vyom reload` after editing.

## Troubleshooting

- **Nothing opens.** `vyom list` shows every installed tool, and why one is skipped (a missing requirement, or a Vyom that's too old).
- **It opened, then something failed.** Look for a `Traceback` in the daemon's log, `journalctl --user -u vyom -u vyom-daemon -b` (without systemd: `~/.local/state/vyom/daemon.log`), and [open an issue](https://github.com/Theyashsawarkar/mudra/issues/new/choose) with it.
- **No blur or rounded corners.** That's the compositor: on SwayFX, add `layer_effects "vyom" { blur enable; corner_radius 20; shadows enable }`.

## The Vyom family

Each tool is its own repository, so you install only the ones you want:

| Tool | | What it does |
|---|---|---|
| [dvara](https://github.com/Theyashsawarkar/dvara) | द्वार, gateway | The app launcher |
| [ganit](https://github.com/Theyashsawarkar/ganit) | गणित, mathematics | The calculator and converter |
| [smriti](https://github.com/Theyashsawarkar/smriti) | स्मृति, memory | Clipboard history |
| [bhava](https://github.com/Theyashsawarkar/bhava) | भाव, feeling, emotion | The emoji picker |
| [tarang](https://github.com/Theyashsawarkar/tarang) | तरंग, wave | Wi‑Fi and the hotspot |
| [setu](https://github.com/Theyashsawarkar/setu) | सेतु, bridge | Bluetooth |
| [doot](https://github.com/Theyashsawarkar/doot) | दूत, messenger | Your phone, through KDE Connect |
| [patra](https://github.com/Theyashsawarkar/patra) | पात्र, vessel | Docker containers |
| [akashvani](https://github.com/Theyashsawarkar/akashvani) | आकाशवाणी, voice from the sky | Notifications |
| [raga](https://github.com/Theyashsawarkar/raga) | राग, melody | YouTube music and video |
| [mudra](https://github.com/Theyashsawarkar/mudra) (this one) | मुद्रा, gesture | Keybinding search |
| [urja](https://github.com/Theyashsawarkar/urja) | ऊर्जा, energy | The battery at a glance |
| [vishram](https://github.com/Theyashsawarkar/vishram) | विश्राम, rest | The power menu |
| [kendra](https://github.com/Theyashsawarkar/kendra) | केन्द्र, centre | Quick settings |

## Contributing

Bug reports, ideas and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and the few rules every tool follows, and [CHANGELOG.md](CHANGELOG.md) for what changed in each release. Please report security issues privately ([SECURITY.md](SECURITY.md)).

## License

[MIT](LICENSE).
