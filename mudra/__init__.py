"""mudra (मुद्रा, "gesture"): keybinding search for Vyom.

Every keybinding by what it does, with real key caps, grouped by app. The
bindings come from a command that prints them as JSON (Vayu's
keybind-search.py --json, set with `source_command`); without one, mudra
reads sway's own config. Enter runs the binding: a sway one through
swaymsg, a tmux one replayed into your most recent tmux client; anything
else copies its keys.
"""
import json
import os
import re
import shutil
import threading
import zlib
from pathlib import Path

from gi.repository import GLib, Gtk
from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

from . import vim

# KEYBINDS (generated from mudra/vim.py by scripts/keybinds.py; don't edit by hand)
# keybind: Vyom/mudra:insert | Enter | Run the selected keybinding (sway and tmux), else copy its keys
# keybind: Vyom/mudra:normal | Enter | Run the selected keybinding (sway and tmux), else copy its keys
# keybind: Vyom/mudra:normal | y y | Copy the selected keybinding's keys
# keybind: Vyom/mudra:normal | o | Open the file that defines it in $EDITOR (at its line when known)
# keybind: Vyom/mudra leader:normal | Space t a / Space t 1..9 | Switch to All / that app's tab
# keybind: Vyom/mudra leader:normal | Space f c | Show only clashes (or everything again)
# keybind: Vyom/mudra leader:normal | Space f m | Show only one mode's keys: normal, then insert, then every mode
# keybind: Vyom/mudra leader:normal | Space f d | Hide built-in keys (or show them again)
# keybind: Vyom/mudra leader:normal | Space f k | Search by keys only: dd, gg, x (or by words again)
# keybind: Vyom/mudra leader:normal | Space f l | Show every Space-leader key of every tool (the Leader tab)
# keybind: Vyom/mudra leader:normal | Space f f | Search again (clear the box and type)
# keybind: Vyom/mudra leader:normal | Space y y | Copy the selected keybinding's keys
# keybind: Vyom/mudra leader:normal | Space y d | Copy the selected keybinding's description
# keybind: Vyom/mudra leader:normal | Space y c | Copy the selected keybinding's command
# keybind: Vyom/mudra leader:normal | Space o e | Open the file that defines it in $EDITOR
# keybind: Vyom/mudra leader:normal | Space r | Read every keybinding again
# END KEYBINDS

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
    """Bindings that collide: the same keys in the same app, scope, key
    table and mode, both from a config you wrote (a built-in one is simply
    replaced by yours), or both a tool's keys for one mode (a tool that
    says which mode a key works in has one meaning per key there)."""
    if e.get("origin") not in ("custom", "plugin") and not (e.get("origin") == "script" and e.get("mode")):
        return []
    return [(e["source"], e.get("scope") or "", e.get("table") or "", e.get("mode") or "",
             " ".join(seq_tokens(k.strip())))
            for k in e.get("keys", "").split(" / ") if k.strip()]


def prefix_clashes(entries):
    """{id(e): [other]} where one key starts another in the same tool, view
    and mode (g beside g g): the longer one can never be typed."""
    by = {}
    for e in entries:
        if e.get("origin") == "script" and e.get("mode"):
            by.setdefault((e["source"], e.get("scope") or "", e["mode"]), []).append(e)
    out = {}
    for es in by.values():
        seqs = [(tuple(seq_tokens(a.strip())), e) for e in es for a in e.get("keys", "").split(" / ") if a.strip()]
        whole = {}
        for q, e in seqs:
            whole.setdefault(q, e)
        for q, e in seqs:
            for n in range(1, len(q)):
                short = whole.get(q[:n])
                if short is not None and short is not e:
                    out.setdefault(id(e), []).append(short)
                    out.setdefault(id(short), []).append(e)
    return out


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


# Single keys spelled in full; any other lowercase run of 2-3 letters
# ("gg", "dd", "cw") is a vim sequence of single keys.
KEY_WORDS = {"esc", "tab", "end", "del", "ins", "spc"}
LEADER_WORDS = {"space", "spc", "<leader>", "leader", "␣"}


def seq_tokens(alt):
    """One alternative's keys as tokens: 'Space y y' -> [Space, y, y],
    'gg' -> [g, g], 'Ctrl+a s' -> [Ctrl+a, s]. Prose and ranges ('1..9',
    'new name + Enter', 'Enter (counting down)') stay one token."""
    if re.search(r"[()–,]|\.\.|\bthen\b|\s\+\s|\s-\s", alt):
        return [alt.strip()]
    out = []
    for t in alt.split():
        if re.fullmatch(r"[a-z]{2,3}", t) and t not in KEY_WORDS:
            out.extend(t)
        else:
            out.append(t)
    return out


def is_sequence(toks):
    """A vim/leader sequence (Space y y, g g) rather than a chord then a key
    (Ctrl+a s): its first key has no modifier."""
    return len(toks) > 1 and "+" not in toks[0]


def cap_text(k, in_chord):
    """A key's cap: a bare letter keeps its case (g g is not G); inside a
    modifier chord a letter is written in capitals (Super+Q)."""
    return k.upper() if in_chord and len(k) == 1 else k


def keycaps(keys, lead=None):
    """'Super+Shift+q' -> key caps (Pango, in the theme's colours, like every
    Vyom footer); 'Ctrl+a Enter' -> a chord, joined by "then"; 'Space y y'
    -> a sequence, joined by a quiet ›, the Space cap in `lead` (the
    accent)."""
    try:
        from vyom.panel import KEYCAP as cap
    except ImportError:   # Vyom before 0.4: its old fixed colours
        cap = {"bg": "#313244", "fg": "#bac2de", "dim": "#7f849c"}
    if " / " in keys:   # alternatives: "Ctrl+Tab / Ctrl+Shift+Tab"
        return f" <span foreground='{cap['dim']}'>or</span> ".join(keycaps(k, lead) for k in keys.split(" / "))
    toks = seq_tokens(keys)
    out = []
    for chord in toks:
        caps = []
        parts = re.split(r"\+(?=.)", chord) if len(toks) > 1 or " " not in chord else [chord]
        for k in parts:
            fg = lead if (lead and k == "Space") else cap["fg"]
            caps.append(f"<span background='{cap['bg']}' foreground='{fg}' font_family='JetBrainsMono Nerd Font'>"
                        f" {GLib.markup_escape_text(cap_text(k, len(parts) > 1))} </span>")
        out.append(" ".join(caps))
    sep = f" <span foreground='{cap['dim']}'>›</span> " if is_sequence(toks) else \
        f" <span foreground='{cap['dim']}'>then</span> "
    return sep.join(out)


MOD_WORDS = {"super": "super", "win": "super", "mod": "super", "ctrl": "ctrl", "control": "ctrl",
             "alt": "alt", "meta": "alt", "shift": "shift", "prefix": "prefix"}


def key_query(q):
    """'ctrl+h', 'super q', 'alt 1', 'prefix s' -> the set of key parts it
    names, when it looks like keys (it names a modifier); else None.
    Leader sequences ("space y") are seq_query's."""
    parts = [p for p in re.split(r"[\s+]+", q.lower().strip()) if p]
    if len(parts) < 2 or not any(p in MOD_WORDS and len(p) > 1 for p in parts):
        return None
    return {MOD_WORDS.get(p, p) for p in parts}


def seq_query(q):
    """'space y', 'spc t c', '<leader>y' -> the key sequence it names, in
    order ([Space, y]), when it starts with a leader word; else None."""
    q = re.sub(r"<leader>", " space ", q.strip(), flags=re.I)
    words = q.split()
    if not words or words[0].lower() not in LEADER_WORDS:
        return None
    seq = ["Space"]
    for w in words[1:]:
        seq.extend(seq_tokens(w))
    return seq


def seq_match(seq, keys):
    """How far past the typed sequence a binding goes (0 = exactly it), or
    None: keys match in order, as a prefix ("space y" lists the whole Copy
    group), letters by case."""
    best = None
    for alt in keys.split(" / "):
        toks = seq_tokens(alt)
        if len(toks) >= len(seq) and all(a == b or (len(a) > 1 and a.lower() == b.lower())
                                          for a, b in zip(toks, seq)):
            d = len(toks) - len(seq)
            best = d if best is None else min(best, d)
    return best


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


# The Space grammar (Vayu's docs/KEYBINDINGS.md): leader groups that mean
# the same thing in every tool, and the first words their keys may start
# with. The Leader tab flags a key that uses one for something else.
RESERVED = {
    "q": ("close", {"close", "quit", "leave", "exit", "hide"}),
    "t": ("tabs", {"switch", "go", "show", "open", "jump", "focus", "move"}),
    "u": ("UI toggles", {"toggle", "show", "hide", "turn", "switch", "enter", "leave", "invert", "zoom", "fit"}),
    "y": ("copy", {"copy", "yank", "save"}),
    "f": ("find / filter", {"find", "filter", "search", "show", "clear", "hide", "pick", "open", "jump", "toggle"}),
    "s": ("sort", {"sort", "order", "reverse"}),
    "r": ("refresh", {"refresh", "reload", "rescan", "update", "sync", "fetch", "search", "retry", "resync"}),
    "a": ("add / new", {"add", "create", "new", "save", "pair", "start", "accept", "write", "make", "compose",
                        "send", "attach", "connect"}),
    "d": ("delete", {"delete", "remove", "clear", "forget", "dismiss", "kill", "prune", "unpair", "disconnect",
                     "stop", "drop", "reject", "trash", "close", "cancel", "take", "decline", "archive"}),
    "e": ("edit", {"edit", "rename", "pick", "change", "set", "open"}),
    "o": ("open outside", {"open", "run", "show", "browse", "play"}),
    "g": ("go to", {"go", "jump", "switch", "show", "open", "focus", "move", "check"}),
    "m": ("mark", {"mark", "toggle", "pin", "unpin", "star", "unstar", "label", "flag", "move", "set"}),
    ",": ("settings", {"open", "show", "edit", "change", "set", "toggle", "sign", "connect"}),
    "k": ("ask the AI", {"ask", "summarize", "draft", "write", "explain", "show", "open", "talk", "send"}),
}


def grammar_clash(e):
    """'Space m is mark in every tool' when a leader key uses a reserved
    group for something else, else ''."""
    for alt in e.get("keys", "").split(" / "):
        toks = seq_tokens(alt)
        if len(toks) >= 3 and toks[0] == "Space" and toks[1] in RESERVED:
            meaning, verbs = RESERVED[toks[1]]
            words = (e.get("desc") or "").split()
            verb = words[0].split("/")[0].lower() if words else ""
            if verb not in verbs:
                return f"Space {toks[1]} is {meaning} in every tool"
    return ""


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


def grammar_order(group):
    """A tool's keys in which-key order when they say their mode: Normal
    direct keys, then the Space tree by sequence (each group together),
    then Insert and the rest. Keys without a mode keep their order."""
    if not any(e.get("mode") or e.get("leader") for e in group):
        return group

    def rank(e):
        if e.get("leader"):
            return (1, seq_tokens(e.get("keys", "").split(" / ")[0]))
        return ({"normal": 0, None: 0, "visual": 2, "command": 3, "insert": 4}.get(e.get("mode"), 2), [])
    return sorted(group, key=rank)


class Plugin(Base):
    name, title, icon, color = "mudra", "Keybindings", "\U000f030c", "lavender"
    placeholder = "What to do, or which keys…  kill window · ctrl+h · space y"
    preview = True
    preview_width = 330
    hints = [Hint("Enter", "run it"), Hint("y y", "copy keys"), Hint("o", "open its file"), Hint("Space f", "filter")]
    insert_hints = [Hint("Enter", "run it"), Hint("Esc", "normal mode")]
    modal = True             # Vyom's vim keys (ADR 0008); mudra/vim.py
    start_mode = "insert"    # search-first
    key_groups = vim.GROUPS
    empty_text = "No keybinding does that"

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.entries = []
        self.clashes = {}
        self.prefixed = {}
        self.misused = {}
        self.small = set()
        self.loaded = False
        self.tab = "all"
        self.only_clash = False      # Space f c
        self.want_mode = ""          # Space f m: "normal" | "insert" | ""
        self.hide_builtin = False    # Space f d
        self.keys_only = False       # Space f k: the query is keys (dd, gg)
        self.peach = "#fab387"
        self.accent = "#cba6f7"
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
        self.prefixed = prefix_clashes(entries)
        self.misused = {id(e): why for e in entries if e.get("leader") for why in [grammar_clash(e)] if why}
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
        # Every Space-leader key of every tool, by tool and sequence: the
        # which-key trees side by side, with keys that break the grammar
        # marked.
        leader = sum(1 for e in self.entries if e.get("leader"))
        if leader:
            tabs.append(("leader", "Leader", f"{leader} Space-leader keys"))
        self.set_tabs(tabs, self.tab)
        return False

    def opened(self, args):
        super().opened(args)
        self.peach = theme_hex("peach", "#fab387")
        self.accent = theme_hex("accent", "#cba6f7")
        self.loaded = False  # bindings change as you edit configs: re-read on every open, behind the panel

    def search(self, q):
        if not self.entries:
            self.load()
        elif not self.loaded:
            self.loaded = True
            threading.Thread(target=self.reload_in_background, daemon=True).start()
        q = q.strip()
        if self.keys_only and q and not q.lower().split()[0] in LEADER_WORDS:
            sq = [t for w in q.split() for t in seq_tokens(w)]
        else:
            sq = None
        sq = sq or (seq_query(q) if q else None)
        kq = key_query(q) if q and sq is None else None
        scored = []
        for i, e in enumerate(self.entries):
            if self.tab == "other" and e["source"] not in self.small:
                continue
            if self.tab == "leader" and not e.get("leader"):
                continue
            if self.tab not in ("all", "other", "leader") and e["source"] != self.tab:
                continue
            default = e.get("origin") == "default"
            if self.hide_builtin and default:
                continue
            if self.want_mode and e.get("mode") != self.want_mode:
                continue
            if self.only_clash and not self.clash_of(e):
                continue
            if not q:
                scored.append((5 if default else 0, i, e))
                continue
            if sq is not None:   # "space y": the whole group under it, shortest first
                d = seq_match(sq, e.get("keys", ""))
                if d is not None:
                    scored.append((d + (5 if default else 0), i, e))
                continue
            if kq is not None:   # typed keys: bindings whose keys hold all of them
                parts = key_parts(e.get("keys", ""))
                if kq <= parts:
                    scored.append((len(parts) - len(kq) + (5 if default else 0), i, e))
                continue
            # What it does, where, and in which app ("tmux kill" finds tmux's)
            text = (f"{e.get('desc', '')} {e.get('scope') or ''} {e['source']} {self.tool_words(e)}"
                    f" {e.get('mode') or ''} {'leader' if e.get('leader') else ''} {' '.join(e.get('group') or ())}")
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
        words = q.lower().split() if q and kq is None and sq is None else []
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
                group = grammar_order(group)
                clash = sum(1 for e in group if self.clash_of(e))
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

    def clash_of(self, e):
        """Why this binding clashes ('' when it doesn't): the same keys twice
        in one mode, a key that starts a longer one, or a leader group used
        against the grammar (the Leader tab's red chip)."""
        if id(e) in self.clashes:
            return "these keys do two things here"
        if id(e) in self.prefixed:
            return "one of these keys starts the other, so the longer one can never be typed"
        if self.tab == "leader" and id(e) in self.misused:
            return self.misused[id(e)]
        return ""

    def row(self, e, words=()):
        src = e["source"]
        scope = " · ".join(x for x in (self.where(e), "built-in" if e.get("origin") == "default" else "") if x)
        # Neutral chips (no colour that means something): the vim mode the
        # key works in, and "leader" for a Space key. Red only for a clash.
        chips = [(e["mode"], "gray")] if e.get("mode") else []
        if e.get("leader"):
            chips.append(("leader", "gray"))
        if self.clash_of(e):
            chips.append(("Clash", "red"))
        return Row(highlight(e.get("desc", ""), words, self.peach), GLib.markup_escape_text(scope),
                   icon=src, color=app_color(src), meta=keycaps(e.get("keys", ""), self.accent), markup=True,
                   dim=e.get("origin") == "default", chips=chips or None, data=e)

    def big_keys(self, keys):
        """The keys as big caps: chords joined by "then", a vim or leader
        sequence by ›, alternatives by "or"; bare letters keep their case."""
        box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6,
                          max_children_per_line=12, homogeneous=False, valign=Gtk.Align.START)
        box.add_css_class("chips")
        for a, alt in enumerate(k for k in keys.split(" / ") if k):
            if a:
                box.append(ui.label("or", "mudra-then", valign=Gtk.Align.CENTER))
            toks = seq_tokens(alt)
            for c, chord in enumerate(toks):
                if c:
                    box.append(ui.label("›" if is_sequence(toks) else "then", "mudra-then", valign=Gtk.Align.CENTER))
                parts = re.split(r"\+(?=.)", chord) if " " not in chord else [chord]
                for k in parts:
                    cap = ui.label(cap_text(k, len(parts) > 1), "keycap", "mudra-bigcap")
                    if k == "Space":
                        cap.add_css_class("mudra-lead")
                    box.append(cap)
        return box

    def path_text(self, e):
        """The which-key path: 'Space › y Copy › y the answer'."""
        toks = seq_tokens(e.get("keys", "").split(" / ")[0])
        if not (e.get("leader") and toks and toks[0] == "Space"):
            return ""
        names = list(e.get("group") or ())
        out = ["Space"]
        for i, t in enumerate(toks[1:]):
            last = i == len(toks) - 2
            name = e.get("desc", "") if last else (names[i] if i < len(names) else "")
            out.append(f"{t} {name}".strip())
        return " › ".join(out)

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
        if e.get("mode"):
            facts.append(("Mode", f"{e['mode']} mode"))
        if self.path_text(e):
            facts.append(("Path", self.path_text(e)))
        if e.get("origin"):
            facts.append(("Kind", {"default": "built in", "custom": "yours", "plugin": "a plugin's",
                                   "script": "inside a tool"}.get(e["origin"], e["origin"])))
        if facts:
            parts.append(ui.kv(facts))
        if e.get("command"):
            parts.append(ui.vbox(ui.label("Does", "kv-key", xalign=0), ui.mono(e["command"]), spacing=4))
        why = self.clash_of(e)
        if why:
            others = self.clashes.get(id(e)) or self.prefixed.get(id(e)) or []
            parts.append(ui.notice(f"Clash: {why}",
                                   ("Also: " + "; ".join(o.get("desc", "") for o in others[:3])) if others else
                                   "Pick another letter for it (Vayu's docs/KEYBINDINGS.md, the Space grammar)", "red"))
        btns = [("Run it" if self.runnable(e) else "Copy keys", lambda: self.run_entry(e), "primary", "", "Enter")]
        if self.runnable(e):
            btns.append(("Copy keys", lambda: self.copy_keys(e), "", "", "y y"))
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

    # ================================================================ keys
    # The modes, counts and sequences are Vyom's; mudra/vim.py is its keys.
    def keys(self, tab):
        return vim.keys(tab)

    def chosen(self):
        row = self.panel.selected_row() if self.panel else None
        return row.data if row is not None and row.data else None

    def v_copy(self, _n, arg):
        e = self.chosen()
        if e is None:
            return
        text = {"keys": e.get("keys", ""), "desc": e.get("desc", ""), "cmd": e.get("command") or ""}[arg]
        if not text:
            self.set_status("it has no command to copy", kind="bad")
            return
        util.copy(text)
        self.set_status(f"copied {text}", kind="ok")

    def v_editor(self, _n, _a):
        e = self.chosen()
        where = defined_in(e) if e is not None else ""
        if not where:
            self.set_status("no file is known for this one", kind="bad")
            return
        path, _, line = where.rpartition(":") if re.search(r":\d+$", where) else (where, "", "")
        path = os.path.expanduser(path)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
        term = self.conf.get("terminal") or os.environ.get("TERMINAL") or \
            next((t for t in ("kitty", "foot", "alacritty", "wezterm") if shutil.which(t)), "xterm")
        util.spawn([term, "-e", editor] + ([f"+{line}"] if line else []) + [path])
        self.close()

    def v_filter(self, _n, arg):
        if arg == "leader":
            if any(t[0] == "leader" for t in self.tabs):
                self.select_tab("leader")
            else:
                self.set_status("no tool has Space-leader keys yet", kind="bad")
            return
        if arg == "clash":
            self.only_clash = not self.only_clash
            msg = "showing only clashes" if self.only_clash else "showing every keybinding"
        elif arg == "mode":
            self.want_mode = {"": "normal", "normal": "insert"}.get(self.want_mode, "")
            msg = f"showing only {self.want_mode} mode" if self.want_mode else "showing every mode"
        elif arg == "builtin":
            self.hide_builtin = not self.hide_builtin
            msg = "hiding built-in keys" if self.hide_builtin else "showing built-in keys"
        else:
            self.keys_only = not self.keys_only
            msg = "searching by keys (dd, gg)" if self.keys_only else "searching by words"
        self.set_status(msg)
        self.refresh()

    def v_reload(self, _n, _a):
        self.set_status("reading every keybinding again…")
        threading.Thread(target=self.reload_in_background, daemon=True).start()
