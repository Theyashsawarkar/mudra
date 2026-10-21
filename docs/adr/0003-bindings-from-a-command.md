# 3. Read bindings from a command that prints JSON

**Status:** Accepted  
**Date:** 2026-10-19

## Context

Keybindings live in many configs (sway, tmux, kitty, editors, tools). Parsing them all inside a panel would duplicate a parser that already exists.

## Decision

mudra runs a source command that prints the bindings as JSON (Vayu's `keybind-search.py --json`), and falls back to reading sway's config when there isn't one.

## Consequences

- One registry for the whole desktop.
- Running a binding replays it through swaymsg or tmux.
