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
import threading
import zlib
from pathlib import Path

from gi.repository import GLib, Gtk
from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/keybindings | Enter | Run the selected keybinding (sway and tmux), else copy its keys
# keybind: Vyom/keybindings | Ctrl+C | Copy the selected keybinding's keys

# One colour per app, the same everywhere (its chip at the left of a row,
# its tab, the preview). Never peach (what you searched for) or red (a clash).
COLORS = {"Sway": "blue", "Tmux": "green", "Kitty": "pink", "Zed": "sky", "rmpc": "mauve", "Kernel": "rose",
          "Vyom": "mauve", "Vayu": "lavender", "Nada": "teal", "Vesha": "lavender", "Vinyasa": "sky",
          "Dvarapala": "rose", "Pramana": "lavender", "Drishya": "teal", "Vishvakarma": "pink", "Ekatva": "teal"}
PALETTE = ["teal", "lavender", "sky", "pink", "rose", "blue", "mauve"]

HOME = Path.home()
# Where a binding is written, to say "Defined in <file>:<line>".
CONFIGS = {"Sway": HOME / ".config/sway/config", "Kitty": HOME / ".config/kitty/kitty.conf",
           "Zed": HOME / ".config/zed/keymap.json"}


def app_color(src):
    return COLORS.get(src) or PALETTE[zlib.crc32(src.encode()) % len(PALETTE)]


def theme_hex(name, fallback):
    """A theme colour (@peach...) as #rrggbb for Pango markup, read from the
    loaded CSS through a label (main thread only)."""
    try:
        w = Gtk.Label()
        w.add_css_class(f"t-{name}")
        c = w.get_color()
        return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))
    except (AttributeError, TypeError):
        return fallback


def highlight(text, words, color):
    """`text` escaped for Pango, every word of the query in it in `color`."""
    low, marks = text.lower(), [False] * len(text)
    for w in words:
        if len(w) < 2:
            continue
        i = low.find(w)
        while i >= 0:
            for j in range(i, i + len(w)):
                marks[j] = True
            i = low.find(w, i + len(w))
    out, i = [], 0
    while i < len(text):
        j = i
        while j < len(text) and marks[j] == marks[i]:
            j += 1
        part = GLib.markup_escape_text(text[i:j])
        out.append(f"<span foreground='{color}'>{part}</span>" if marks[i] else part)
        i = j
    return "".join(out)


def clash_key(e):
    """Bindings that collide: the same keys in the same app, scope and key
    table, both from a config you wrote (a tool's own keys change with its
    screen, and a built-in one is simply replaced by yours)."""
    if e.get("origin") not in ("custom", "plugin"):
        return []
    return [(e["source"], e.get("scope") or "", e.get("table") or "", k.strip())
            for k in e.get("keys", "").split(" / ") if k.strip()]


def defined_in(e):
    """'~/.config/sway/config:142' when the binding's line can be found,
    else the file a tool's binding came from, else ''."""
    path, cmd = CONFIGS.get(e["source"]), (e.get("command") or "").strip()
    if path and cmd:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            lines = []
        for n, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if (e["source"] == "Sway" and s.startswith("bind") and s.endswith(cmd)) or \
               (e["source"] == "Kitty" and s.startswith("map ") and s.endswith(cmd)) or \
               (e["source"] == "Zed" and f'"{cmd}"' in s):
                return f"{str(path).replace(str(HOME), '~')}:{n}"
    return e.get("file") or ""


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
    placeholder = "What to do, or which keys…  kill window · ctrl+h"
    preview = True
    preview_width = 330
    hints = [Hint("Enter", "run it"), Hint("Ctrl+C", "copy keys")]
    empty_text = "No keybinding does that"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.entries = []
        self.clashes = {}
        self.small = set()
        self.loaded = False
        self.tab = "all"
        self.peach = "#fab387"
        # read ahead, so even the first open has them
        threading.Thread(target=self.load, daemon=True).start()

    def read_entries(self):
        """Every binding, or None when the source can't say."""
        cmd = self.conf.get("source_command") or ("keybind-search.py --json" if util.have("keybind-search.py") else "")
        if not cmd:
            return None
        code, out = util.run(cmd, timeout=20)
        try:
            return (json.loads(out) if code == 0 else None) or None
        except ValueError:
            return None

    def set_entries(self, entries):
        by_key = {}
        for e in entries:
            for k in clash_key(e):
                by_key.setdefault(k, []).append(e)
        clashes = {}
        for k, es in by_key.items():
            if len({id(e) for e in es}) > 1:
                for e in es:
                    clashes.setdefault(id(e), []).extend(o for o in es if o is not e)
        self.entries, self.clashes = entries, clashes

    def load(self):
        self.set_entries(self.read_entries() or self.entries or from_sway())
        self.loaded = True
        GLib.idle_add(self.build_tabs)

    def reload_in_background(self):
        """Reading every config takes seconds: the panel opens at once on what
        it knows, and catches up here. A failed read keeps what it has."""
        entries = self.read_entries()
        if entries and entries != self.entries:
            self.set_entries(entries)
            GLib.idle_add(self.build_tabs)
            GLib.idle_add(self.refresh)

    def build_tabs(self):
        """One tab per app that has keybindings, with how many ("Sway 106";
        Ctrl+H/L, Ctrl+1..9: Vyom)."""
        # Most bindings first (Sway, Tmux, Vyom...): the ones you jump to get
        # the low numbers. All of them, not just ten (Tab reaches the rest).
        count = {}
        for e in self.entries:
            count[e["source"]] = count.get(e["source"], 0) + 1
        sources = sorted(count, key=lambda s: (-count[s], s))
        # Ten tabs at most (Ctrl+1..9, Ctrl+0): the eight biggest apps, and
        # the small ones together under "Other". Names only: each tab's count
        # is in its tooltip and on its sections.
        big, small = sources[:8], sources[8:]
        if len(small) == 1:
            big, small = sources, []
        self.small = set(small)
        tabs = [("all", "All", f"{len(self.entries)} keybindings")]
        tabs += [(s, s, f"{count[s]} keybindings") for s in big]
        if small:
            tabs.append(("other", "Other", ", ".join(small)))
        self.set_tabs(tabs, self.tab)
        return False

    def opened(self, args):
        super().opened(args)
        self.peach = theme_hex("peach", "#fab387")
        self.loaded = False  # bindings change as you edit configs: re-read on every open, behind the panel

    def search(self, q):
        if not self.entries:
            self.load()
        elif not self.loaded:
            self.loaded = True
            threading.Thread(target=self.reload_in_background, daemon=True).start()
        q = q.strip()
        kq = key_query(q) if q else None
        scored = []
        for i, e in enumerate(self.entries):
            if self.tab == "other" and e["source"] not in self.small:
                continue
            if self.tab not in ("all", "other") and e["source"] != self.tab:
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
            text = f"{e.get('desc', '')} {e.get('scope') or ''} {e['source']} {self.tool_words(e)}"
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
        words = q.lower().split() if q and kq is None else []
        if q:   # searching: one list, best first, the app's chip on each row
            return [self.row(e, words) for _, _, e in scored[:300]]
        rows, by_src = [], {}
        for _, _, e in scored:
            by_src.setdefault(e["source"], []).append(e)
        for src, items in by_src.items():
            # Vyom is one app made of many tools: a section per tool, every
            # panel's own keys first, the rest by name.
            groups = [(src, "", items)]
            if src == "Vyom":
                by_tool = {}
                for e in items:
                    by_tool.setdefault(e.get("tool") or "vyom", []).append(e)
                order = sorted(by_tool, key=lambda t: (t != "vyom", t))
                groups = [("Vyom · every panel", "", by_tool[t]) if t == "vyom" else
                          (f"Vyom · {t}", self.tool_title(t), by_tool[t]) for t in order]
            for title, what, group in groups:
                clash = sum(1 for e in group if id(e) in self.clashes)
                note = " · ".join(x for x in (what, f"{clash} clash{'es' if clash > 1 else ''}" if clash else "") if x)
                rows.append(Section(title, len(group), note))
                rows += [self.row(e) for e in group]
        return rows

    def tool_title(self, tool):
        """A Vyom tool's title ("ganit" -> "Calculator")."""
        if tool == "vyom":
            return "every panel"
        p = getattr(self.vyom, "plugins", {}).get(tool)
        return getattr(p, "title", "") or ""

    def tool_words(self, e):
        """What a Vyom key is also found by: its tool's name and title."""
        t = e.get("tool")
        return f"{t} {self.tool_title(t)}" if t else ""

    def where(self, e):
        """Its row's second line: the Vyom tool, then the part of it
        ("ganit · converter"), else the scope."""
        scope, t = e.get("scope") or "", e.get("tool")
        if t and t != "vyom":
            part = scope[len(t):].strip(" -·") if scope.lower().startswith(t) else scope
            if part.lower().replace("-", "") == self.tool_title(t).lower().replace("-", ""):
                part = ""   # akashvani's "notifications" says what its title does
            scope = " · ".join(x for x in (t, part) if x)
        return scope

    def row(self, e, words=()):
        src = e["source"]
        scope = " · ".join(x for x in (self.where(e), "built-in" if e.get("origin") == "default" else "") if x)
        return Row(highlight(e.get("desc", ""), words, self.peach), GLib.markup_escape_text(scope),
                   icon=src, color=app_color(src), meta=keycaps(e.get("keys", "")), markup=True,
                   dim=e.get("origin") == "default", chips=[("Clash", "red")] if id(e) in self.clashes else None,
                   data=e)

    def big_keys(self, keys):
        """The keys as big caps: chords joined by "then", alternatives by "or"."""
        box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6,
                          max_children_per_line=12, homogeneous=False, valign=Gtk.Align.START)
        box.add_css_class("chips")
        for a, alt in enumerate(k for k in keys.split(" / ") if k):
            if a:
                box.append(ui.label("or", "mudra-then", valign=Gtk.Align.CENTER))
            for c, chord in enumerate(x for x in alt.split(" ") if x):
                if c:
                    box.append(ui.label("then", "mudra-then", valign=Gtk.Align.CENTER))
                for k in re.split(r"\+(?=.)", chord):
                    box.append(ui.label(k if len(k) > 1 else k.upper(), "keycap", "mudra-bigcap"))
        return box

    def build_preview(self, row):
        e = row.data
        src = e["source"]
        parts = [ui.chip(src, app_color(src)), ui.title(e.get("desc", "")), self.big_keys(e.get("keys", ""))]
        facts = []
        where = defined_in(e)
        if where:
            facts.append(("Defined in", where))
        if self.where(e):
            facts.append(("Where", self.where(e)))
        if e.get("origin"):
            facts.append(("Kind", {"default": "built in", "custom": "yours", "plugin": "a plugin's",
                                   "script": "inside a tool"}.get(e["origin"], e["origin"])))
        if facts:
            parts.append(ui.kv(facts))
        if e.get("command"):
            parts.append(ui.vbox(ui.label("Does", "kv-key", xalign=0), ui.mono(e["command"]), spacing=4))
        others = self.clashes.get(id(e))
        if others:
            parts.append(ui.notice("Clash: these keys do two things here",
                                   "Also: " + "; ".join(o.get("desc", "") for o in others[:3]), "red"))
        btns = [("Run it" if self.runnable(e) else "Copy keys", lambda: self.run_entry(e), "primary", "", "Enter")]
        if self.runnable(e):
            btns.append(("Copy keys", lambda: self.copy_keys(e), "", "", "Ctrl+C"))
        parts.append(ui.buttons(btns))
        return ui.vbox(*parts, spacing=12)

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

    def copy_keys(self, e):
        util.copy(e.get("keys", ""))
        self.set_status(f"copied {e.get('keys', '')}")

    def activate(self, row, mods):
        self.run_entry(row.data)
        return False

    def key(self, name, row, mods):
        if mods == {"ctrl"} and name == "c" and row is not None:
            self.copy_keys(row.data)
            return True
        return False
