"""mudra (मुद्रा, "gesture"): keybinding search for Vyom.

Every keybinding by what it does, with real key caps, grouped by app. The
bindings come from a command that prints them as JSON (Vayu's
keybind-search.py --json, set with `source_command`); without one, mudra
reads sway's own config. Enter runs the binding: a sway one through
swaymsg, a tmux one replayed into your most recent tmux client; anything
else copies its keys.
"""
import json
import re

from gi.repository import GLib, Gtk

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/keybindings | Enter | Run the selected keybinding (sway and tmux), else copy its keys
# keybind: Vyom/keybindings | Ctrl+C | Copy the selected keybinding's keys
# keybind: Vyom/keybindings | Ctrl+1..9 | Show all, or one app's keybindings

COLORS = {"Sway": "sky", "Tmux": "teal", "Kitty": "pink", "Zed": "blue", "rmpc": "mauve", "Kernel": "red",
          "Vyom": "lavender", "Vayu": "lavender"}
ICONS = {"Sway": "\U000f05a8", "Tmux": "", "Kitty": "\U000f011b", "Zed": "\U000f0a1e", "rmpc": "\U000f075a",
         "Kernel": "\U000f1053", "Vyom": "\U000f0493", "Vayu": "\U000f0493"}


def keycaps(keys):
    """'Super+Shift+q' -> key caps (Pango); 'Ctrl+a Enter' -> a chord."""
    out = []
    for chord in keys.split(" "):
        if not chord:
            continue
        caps = []
        for k in re.split(r"\+(?=.)", chord):
            k = k if len(k) > 1 else k.upper()
            caps.append(f"<span background='#313244' foreground='#bac2de' font_family='JetBrainsMono Nerd Font'> {GLib.markup_escape_text(k)} </span>")
        out.append(" ".join(caps))
    return " <span foreground='#6c7086'>then</span> ".join(out)


def from_sway():
    code, out = util.run(["swaymsg", "-t", "get_config", "-r"], timeout=3)
    try:
        text = json.loads(out)["config"]
    except (ValueError, KeyError):
        return []
    res, desc = [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#:"):
            desc = s[2:].strip()
            continue
        m = re.match(r"^bindsym\s+(?:--\S+\s+)*(\S+)\s+(.+)$", s)
        if m:
            keys = m.group(1).replace("$mod", "Super").replace("Mod4", "Super").replace("Mod1", "Alt")
            res.append({"source": "Sway", "keys": keys, "desc": desc or m.group(2), "command": m.group(2)})
        elif not s.startswith("bindsym"):
            desc = None
    return res


class Plugin(Base):
    name, title, icon, color = "mudra", "Keybindings", "\U000f030c", "lavender"
    placeholder = "What do you want to do?   e.g. kill window, volume, screenshot"
    preview = True
    preview_width = 300
    hints = [Hint("Enter", "run it"), Hint("Ctrl+C", "copy keys"), Hint("Ctrl+1-9", "app")]
    empty_text = "No keybinding does that"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.entries = []
        self.loaded = False
        self.app = "all"
        self.tabs = {}
        self.tab_box = None

    def load(self):
        cmd = self.conf.get("source_command") or ("keybind-search.py --json" if util.have("keybind-search.py") else "")
        entries = []
        if cmd:
            code, out = util.run(cmd, timeout=20)
            try:
                entries = json.loads(out) if code == 0 else []
            except ValueError:
                entries = []
        self.entries = entries or from_sway()
        self.loaded = True
        GLib.idle_add(self.build_tabs)

    def header_extra(self):
        self.tab_box = Gtk.Box(spacing=2)
        return self.tab_box

    def build_tabs(self):
        child = self.tab_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.tab_box.remove(child)
            child = nxt
        self.tabs = {}
        sources = ["all"] + sorted({e["source"] for e in self.entries}, key=lambda s: (s not in COLORS, s))
        group = None
        for s in sources[:9]:
            b = Gtk.ToggleButton(label="All" if s == "all" else s)
            b.add_css_class("tab")
            b.set_can_focus(False)
            if group is None:
                group = b
            else:
                b.set_group(group)
            b.connect("toggled", lambda btn, k=s: btn.get_active() and self.set_app(k))
            self.tabs[s] = b
            self.tab_box.append(b)
        (self.tabs.get(self.app) or self.tabs["all"]).set_active(True)
        return False

    def set_app(self, s):
        self.app = s
        self.refresh()

    def opened(self, args):
        super().opened(args)
        self.loaded = False  # bindings change as you edit configs: re-read on every open

    def search(self, q):
        if not self.loaded:
            self.load()
        scored = []
        for i, e in enumerate(self.entries):
            if self.app != "all" and e["source"] != self.app:
                continue
            text = f"{e.get('desc', '')} {e.get('scope') or ''}"
            s = util.fuzzy(q, text) if q else 0
            if s is None:
                k = util.fuzzy(q, e.get("keys", ""), loose=False)
                if k is None:
                    continue
                s = k / 2
            default = e.get("origin") == "default"
            scored.append((-(s or 0) + (5 if default else 0), i, e))
        scored.sort(key=lambda t: (t[0], t[1]))
        rows, by_src = [], {}
        for _, _, e in scored[:300]:
            by_src.setdefault(e["source"], []).append(e)
        for src, items in by_src.items():
            rows.append(Section(src))
            for e in items:
                scope = " · ".join(x for x in (e.get("scope"), "built-in" if e.get("origin") == "default" else "") if x)
                rows.append(Row(GLib.markup_escape_text(e.get("desc", "")), GLib.markup_escape_text(scope),
                                icon=ICONS.get(src, "\U000f030c"), color=COLORS.get(src, "gray"),
                                meta=keycaps(e.get("keys", "")), markup=True, dim=e.get("origin") == "default",
                                data=e))
        return rows

    def build_preview(self, row):
        e = row.data
        parts = [ui.chip(e["source"], COLORS.get(e["source"], "gray")), ui.title(e.get("desc", "")),
                 ui.label(keycaps(e.get("keys", "")), markup=True, xalign=0, wrap=True)]
        facts = []
        if e.get("scope"):
            facts.append(("Where", e["scope"]))
        if e.get("origin"):
            facts.append(("Kind", {"default": "built in", "custom": "yours", "plugin": "a plugin's",
                                   "script": "inside a tool"}.get(e["origin"], e["origin"])))
        if facts:
            parts.append(ui.kv(facts))
        if e.get("command"):
            parts.append(ui.mono(e["command"]))
        runnable = self.runnable(e)
        parts.append(ui.buttons([("Run it" if runnable else "Copy keys", lambda: self.run_entry(e), "primary")]))
        return ui.vbox(*parts, spacing=10)

    def runnable(self, e):
        return (e["source"] == "Sway" and e.get("command") and util.have("swaymsg")) or \
               (e["source"] == "Tmux" and e.get("tmux_key") and util.have("tmux"))

    def tmux_client(self):
        code, out = util.run(["tmux", "list-clients", "-F", "#{client_activity} #{client_name}"])
        clients = sorted((l.split(" ", 1) for l in out.splitlines() if " " in l), reverse=True)
        return clients[0][1] if clients else None

    def run_entry(self, e):
        self.close()
        if e["source"] == "Sway" and e.get("command"):
            util.spawn(["swaymsg", e["command"]])
            return
        if e["source"] == "Tmux" and e.get("tmux_key"):
            c = self.tmux_client()
            if c:
                key = "\\;" if e["tmux_key"] == ";" else e["tmux_key"]  # a bare ; is tmux's separator
                table = e.get("table", "root")
                if table == "prefix":
                    prefix = util.run(["tmux", "show", "-gv", "prefix"])[1] or "C-b"
                    util.spawn(["tmux", "send-keys", "-K", "-c", c, prefix, key])
                elif table.startswith("copy-mode"):
                    pane = util.run(["tmux", "display", "-p", "-c", c, "#{pane_id}"])[1]
                    util.run(["tmux", "copy-mode", "-t", pane])
                    util.spawn(["tmux", "send-keys", "-K", "-c", c, key])
                else:
                    util.spawn(["tmux", "send-keys", "-K", "-c", c, key])
                return
        util.copy(e.get("keys", ""))
        util.notify("Keybinding", f"Copied {e.get('keys', '')}", app="mudra")

    def activate(self, row, mods):
        self.run_entry(row.data)
        return False

    def key(self, name, row, mods):
        if "ctrl" in mods and name == "c" and row is not None:
            util.copy(row.data.get("keys", ""))
            self.set_status("copied")
            return True
        if "ctrl" in mods and len(name) == 1 and name.isdigit() and name != "0":
            keys = list(self.tabs)
            i = int(name) - 1
            if i < len(keys):
                self.tabs[keys[i]].set_active(True)
            return True
        return False
