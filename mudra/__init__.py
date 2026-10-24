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

from gi.repository import GLib

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/keybindings | Enter | Run the selected keybinding (sway and tmux), else copy its keys
# keybind: Vyom/keybindings | Ctrl+C | Copy the selected keybinding's keys

COLORS = {"Sway": "sky", "Tmux": "teal", "Kitty": "pink", "Zed": "blue", "rmpc": "mauve", "Kernel": "red",
          "Vyom": "lavender", "Vayu": "lavender", "Nada": "peach", "Vesha": "yellow", "Vinyasa": "mauve",
          "Anumati": "red", "Pramana": "yellow"}
ICONS = {"Sway": "\U000f05a8", "Tmux": "", "Kitty": "\U000f011b", "Zed": "\U000f0a1e", "rmpc": "\U000f075a",
         "Kernel": "\U000f1053", "Vyom": "\U000f0493", "Vayu": "\U000f0493", "Nada": "\U000f075a",
         "Vesha": "\U000f0004", "Vinyasa": "\U000f0493", "Anumati": "\U000f0483",
         "Pramana": "\U000f033e"}


def keycaps(keys):
    """'Super+Shift+q' -> key caps (Pango, in the theme's colours, like every
    Vyom footer); 'Ctrl+a Enter' -> a chord."""
    try:
        from vyom.panel import KEYCAP as cap
    except ImportError:   # Vyom before 0.4: its old fixed colours
        cap = {"bg": "#313244", "fg": "#bac2de", "dim": "#6c7086"}
    if " / " in keys:   # alternatives: "Ctrl+Tab / Ctrl+Shift+Tab"
        return f" <span foreground='{cap['dim']}'>or</span> ".join(keycaps(k) for k in keys.split(" / "))
    out = []
    for chord in keys.split(" "):
        if not chord:
            continue
        caps = []
        for k in re.split(r"\+(?=.)", chord):
            k = k if len(k) > 1 else k.upper()
            caps.append(f"<span background='{cap['bg']}' foreground='{cap['fg']}' font_family='JetBrainsMono Nerd Font'>"
                        f" {GLib.markup_escape_text(k)} </span>")
        out.append(" ".join(caps))
    return f" <span foreground='{cap['dim']}'>then</span> ".join(out)


MOD_WORDS = {"super": "super", "win": "super", "mod": "super", "ctrl": "ctrl", "control": "ctrl",
             "alt": "alt", "meta": "alt", "shift": "shift", "prefix": "prefix"}


def key_query(q):
    """'ctrl+h', 'super q', 'alt 1', 'prefix s' -> the set of key parts it
    names, when it looks like keys (it names a modifier); else None."""
    parts = [p for p in re.split(r"[\s+]+", q.lower().strip()) if p]
    if len(parts) < 2 or not any(p in MOD_WORDS and len(p) > 1 for p in parts):
        return None
    return {MOD_WORDS.get(p, p) for p in parts}


def key_parts(keys):
    """A binding's keys as a set: 'Ctrl+a S' -> {prefix, shift, s} (a capital
    letter is Shift and the letter)."""
    keys = keys.replace("Ctrl+a ", "prefix+").replace("Enter", "Return")
    parts = set()
    for p in re.split(r"[\s+/]+", keys):
        if len(p) == 1 and p.isupper():
            parts |= {"shift", p.lower()}
        elif p:
            parts.add(MOD_WORDS.get(p.lower(), p.lower()))
    return parts


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
    placeholder = "What do you want to do, or which keys?   e.g. kill window · screenshot · ctrl+h · super q"
    preview = True
    preview_width = 300
    hints = [Hint("Enter", "run it"), Hint("Ctrl+C", "copy keys")]
    empty_text = "No keybinding does that"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.entries = []
        self.loaded = False
        self.tab = "all"

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

    def build_tabs(self):
        """One tab per app that has keybindings (Ctrl+H/L, Ctrl+1..9: Vyom)."""
        # Most bindings first (Sway, Tmux, Vyom...): the ones you jump to get
        # the low numbers. All of them, not just ten (Ctrl+Tab reaches the rest).
        count = {}
        for e in self.entries:
            count[e["source"]] = count.get(e["source"], 0) + 1
        sources = ["all"] + sorted(count, key=lambda s: (-count[s], s))
        self.set_tabs([(s, "All" if s == "all" else s) for s in sources], self.tab)
        return False

    def opened(self, args):
        super().opened(args)
        self.loaded = False  # bindings change as you edit configs: re-read on every open

    def search(self, q):
        if not self.loaded:
            self.load()
        q = q.strip()
        kq = key_query(q) if q else None
        scored = []
        for i, e in enumerate(self.entries):
            if self.tab != "all" and e["source"] != self.tab:
                continue
            default = e.get("origin") == "default"
            if not q:
                scored.append((5 if default else 0, i, e))
                continue
            if kq is not None:   # typed keys: bindings whose keys hold all of them
                parts = key_parts(e.get("keys", ""))
                if kq <= parts:
                    scored.append((len(parts) - len(kq) + (5 if default else 0), i, e))
                continue
            # What it does, where, and in which app ("tmux kill" finds tmux's)
            text = f"{e.get('desc', '')} {e.get('scope') or ''} {e['source']}"
            s = 0
            low = text.lower().replace("-", "")   # "wifi" finds "Wi-Fi"
            for word in q.lower().replace("-", "").split():   # every word, anywhere ("tmux kill", "window kill")
                if word in low:              # as written: best
                    s += 100 + (50 if re.search(rf"\b{re.escape(word)}", low) else 0)
                    continue
                w = util.fuzzy(word, text, loose=False)
                if w is None:
                    s = None
                    break
                s += w
            if s is None:
                s = util.fuzzy(q, e.get("keys", ""), loose=False)
                if s is None:
                    continue
                s /= 2
            scored.append((-s + (5 if default else 0), i, e))
        scored.sort(key=lambda t: (t[0], t[1]))
        if q:   # searching: one list, best first, the app on each row
            return [self.row(e, badge=True) for _, _, e in scored[:300]]
        rows, by_src = [], {}
        for _, _, e in scored:
            by_src.setdefault(e["source"], []).append(e)
        for src, items in by_src.items():
            rows.append(Section(f"{src} · {len(items)}"))
            rows += [self.row(e) for e in items]
        return rows

    def row(self, e, badge=False):
        src = e["source"]
        scope = " · ".join(x for x in (e.get("scope"), "built-in" if e.get("origin") == "default" else "") if x)
        return Row(GLib.markup_escape_text(e.get("desc", "")), GLib.markup_escape_text(scope),
                   icon=ICONS.get(src, "\U000f030c"), color=COLORS.get(src, "gray"),
                   meta=keycaps(e.get("keys", "")), markup=True, dim=e.get("origin") == "default",
                   badge=src if badge else "", badge_color=COLORS.get(src, "gray"), data=e)

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
        return False
