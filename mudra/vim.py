"""mudra's vim keys, as data. The modes, counts, sequences, which-key strip,
help (?) and palette (Space Space) are Vyom's (vyom/keys.py, vyom/modal.py;
Vyom ADR 0008); this file is only what mudra adds. Space groups follow
Vayu's shared letters: t tabs (Vyom's, one per app), f filter, y copy,
o open outside, r refresh, u toggles.

An action "verb:arg" runs Plugin.v_<verb>(count, arg) in mudra/__init__.py,
or Vyom's own (activate, insert, moved...).
"""
from vyom.keys import Bind

B = Bind

GROUPS = {}

INSERT = [
    ("Enter", "Run the selected keybinding (sway and tmux), else copy its keys"),
]

NORMAL = [
    B("<CR>", "activate", "Run the selected keybinding (sway and tmux), else copy its keys"),
    B("yy", "copy:keys", "Copy the selected keybinding's keys"),
    B("<C-c>", "copy:keys", "", hidden=True),
    B("o", "editor", "Open the file that defines it in $EDITOR (at its line when known)"),
]

LEADER = [
    B(" fc", "filter:clash", "Show only clashes (or everything again)"),
    B(" fm", "filter:mode", "Show only one mode's keys: normal, then insert, then every mode"),
    B(" fd", "filter:builtin", "Hide built-in keys (or show them again)"),
    B(" fk", "filter:keys", "Search by keys only: dd, gg, x (or by words again)"),
    B(" fl", "filter:leader", "Show every Space-leader key of every tool (the Leader tab)"),
    B(" ff", "search", "Search again (clear the box and type)"),
    B(" yy", "copy:keys", "Copy the selected keybinding's keys"),
    B(" yd", "copy:desc", "Copy the selected keybinding's description"),
    B(" yc", "copy:cmd", "Copy the selected keybinding's command"),
    B(" oe", "editor", "Open the file that defines it in $EDITOR"),
    B(" r", "reload", "Read every keybinding again"),
]


def keys(tab):
    return NORMAL + LEADER


SECTIONS = [
    ("mudra", "insert", "Insert mode (typing; mudra opens in it)", INSERT),
    ("mudra", "normal", "Normal mode", NORMAL),
    ("mudra leader", "normal", "Leader (Space)", [("Space t a / Space t 1..9", "Switch to All / that app's tab")]
     + LEADER),
]
