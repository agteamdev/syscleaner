"""GUI logic test on stand-in GTK classes (no display, no GTK needed).

It checks the program logic of the window (state saving, confirmation, history, disk actions, update badge ...),
not the look. Started by tests/test_gui_smoke.py once per language:  python3 tests/gui_smoke.py <repo root>
"""
import json
import os
import sys
import tempfile
import time
import types

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
BASE = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = os.path.join(BASE, "config")
os.environ["XDG_STATE_HOME"] = os.path.join(BASE, "state")
os.makedirs(os.path.join(BASE, "config", "syscleaner", "tasks.d"))
with open(os.path.join(BASE, "config", "syscleaner", "tasks.d", "mine.yaml"), "w", encoding="utf-8") as f:
    f.write('groups:\n  - {id: mine, title: "Mine"}\ntasks:\n  - id: my_root\n    group: mine\n    title: "My root task"\n'
            '    cmd: echo hi\n    root: true\n    schedule: true\n')


# ---------- stand-ins for gi.repository ----------
class Meta(type):
    def __getattr__(cls, name):
        return Stub


class Stub(metaclass=Meta):
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return Stub()
    def __call__(self, *a, **k): return Stub()
    def __iter__(self): return iter(())
    def __getitem__(self, k): return Stub()
    def __setitem__(self, k, v): pass
    def __len__(self): return 0


class Mod:
    def __getattr__(self, n): return Stub


class GErr(Exception):
    def __init__(self, message): super().__init__(message); self.message = message


class GLibMod:
    Error = GErr
    markup_escape_text = staticmethod(lambda s: s.replace("&", "&amp;").replace("<", "&lt;"))
    idle_add = staticmethod(lambda f, *a: None)
    timeout_add_seconds = staticmethod(lambda *a: 0)


class Btn:
    def __init__(self): self.classes = []
    def get_style_context(self): return self
    def add_class(self, c): self.classes.append(c)


class FakeDialog:
    next_response, last = -5, None
    def __init__(self, **kw): self.kw, self.secondary, self.btns = kw, "", []; FakeDialog.last = self
    def format_secondary_text(self, t): self.secondary = t
    def add_button(self, label, resp): b = Btn(); self.btns.append((label, resp, b)); return b
    def set_default_response(self, r): self.default = r
    def run(self): return FakeDialog.next_response
    def destroy(self): pass


class Clip:
    def __init__(self): self.text, self.stored = None, False
    def set_text(self, t, n): self.text = t
    def store(self): self.stored = True
CLIP = Clip()


class Rec:
    """Records what the program sets on a widget."""
    def __init__(self): self.text = self.frac = self.label = self.tip = None; self.classes = []; self.hidden = None
    def set_text(self, t): self.text = t
    def set_visible(self, v): self.visible = v
    def set_sensitive(self, v): self.sensitive = v
    def set_markup(self, t): self.text = t
    def set_fraction(self, f): self.frac = f
    def set_label(self, t): self.label = t
    def set_tooltip_text(self, t): self.tip = t
    def get_style_context(self): return self
    def add_class(self, c): self.classes.append(c)
    def hide(self): self.hidden = True
    def show(self): self.hidden = False


Gtk, Pango, Gdk, Gio = Mod(), Mod(), Mod(), Mod()
Gtk.ResponseType = types.SimpleNamespace(OK=-5, CANCEL=-6, CLOSE=-7)
Gtk.ButtonsType = types.SimpleNamespace(NONE=0, OK=1, OK_CANCEL=3)
Gtk.MessageType = types.SimpleNamespace(INFO=0, WARNING=1, QUESTION=2, ERROR=3)
Gtk.MessageDialog = FakeDialog
Gtk.Clipboard = types.SimpleNamespace(get=lambda sel: CLIP)
Gdk.SELECTION_CLIPBOARD = 1
Gdk.WindowState = types.SimpleNamespace(MAXIMIZED=4)
Gdk.Display = types.SimpleNamespace(get_default=lambda: types.SimpleNamespace(
    get_n_monitors=lambda: 2,
    get_monitor=lambda i: types.SimpleNamespace(get_geometry=lambda: types.SimpleNamespace(
        x=(0, -1920)[i], y=0, width=1920, height=1080))))
gi = types.ModuleType("gi"); gi.require_version = lambda *a: None
repo = types.ModuleType("gi.repository")
repo.Gtk, repo.GLib, repo.Pango, repo.Gdk, repo.Gio = Gtk, GLibMod(), Pango, Gdk, Gio
sys.modules.update({"gi": gi, "gi.repository": repo})

n = 0
def check(cond, label):
    global n
    n += 1
    assert cond, "FAIL: " + label
    print("PASS", label)


from syscleaner import about, gui, history, settings, updater  # noqa: E402
tr, fmt_size = gui._, gui.fmt_size
gui.is_dark = lambda w: False
OK, CANCEL = Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL


class FakeThread:
    started = []
    def __init__(self, target=None, args=(), daemon=None): self.target, self.args = target, args
    def start(self): FakeThread.started.append(self)
gui.threading.Thread = FakeThread
about.threading.Thread = FakeThread

# ---------- window state: save and restore ----------
w = gui.MainWindow()
check(w._ws == {} and w._geom == {}, "first start: nothing to restore")
w.get_size = lambda: (1111, 777); w.get_position = lambda: (123, 45); w.paned.get_position = lambda: 640
w._on_configure(); check(w._geom == {"width": 1111, "height": 777, "x": 123, "y": 45}, "configure-event tracks geometry")
w._on_state(None, types.SimpleNamespace(new_window_state=4)); w.get_size = lambda: (1920, 1080); w._on_configure()
check(w._maximized and w._geom["width"] == 1111, "maximizing does not overwrite the normal size")
w._on_delete()
saved = json.load(open(settings.path()))["window"]
check(saved == {"width": 1111, "height": 777, "x": 123, "y": 45, "maximized": True, "paned": 640}, "state saved on close")
w2 = gui.MainWindow()
check(w2._ws == saved, "state restored on next start")
check(w2._position_ok(123, 45, 1111) and w2._position_ok(-1500, 100, 1000), "positions on connected monitors accepted")
check(not w2._position_ok(5000, 100, 1000), "position on a vanished monitor rejected")

# ---------- selection helpers ----------
class Row(list):
    def __init__(self, vals, kids=()): super().__init__(vals); self._k = kids
    def iterchildren(self): return iter(self._k)
def fresh():
    g = Row([False, "g", "", True, "", ""], [Row([False, "a", "tmp", True, "", ""]), Row([False, "b", "thumbs", True, "", ""]),
                                              Row([False, "c", "snap_old", False, "", ""])])
    w.store = [g]; w.update_total = lambda: None; return g
g = fresh(); w.sel_all(); check(g[0] and g._k[0][0] and g._k[1][0] and not g._k[2][0], "Select all: available tasks only")
w.sel_none(); check(not g[0] and not any(c[0] for c in g._k), "Select none")
g = fresh(); w.sel_safe(); check(g._k[0][0] and g._k[1][0] and not g._k[2][0], "Safe only")

# ---------- custom tasks ----------
by = w.by_id
check(by["my_root"].source == "mine.yaml" and by["my_root"].root and not by["my_root"].schedule, "custom root task is marked and not schedulable")
check(by["thumbs"].source == "", "built-in tasks are not custom")
class Model:
    def __getitem__(self, it): return [False, "", it, True]
class Sel:
    def __init__(self, tid): self.tid = tid
    def get_selected(self): return Model(), self.tid
w.desc = Rec()
w.on_select(Sel("my_root")); check("mine.yaml" in w.desc.text, "details panel names the file of a custom task")
for tid in by: w.on_select(Sel(tid))
check(True, "details panel renders every task")

# ---------- confirmation before running ----------
w.estimates = {"thumbs": 5000}
FakeDialog.next_response = OK
check(w.confirm_run([by["thumbs"]], False), "safe run: confirmed with OK")
d = FakeDialog.last
check(d.kw["message_type"] == Gtk.MessageType.QUESTION and fmt_size(5000) in d.secondary, "safe run: question + size estimate shown")
check(d.btns[-1][2].classes == ["suggested-action"] and d.default == OK, "safe run: normal button style, OK is default")
w.estimates = {}
w.confirm_run([by["thumbs"]], False); check(tr("No size estimate yet. Tip: run “Preview” first.") in FakeDialog.last.secondary, "no estimate yet -> tip to run Preview")
w.confirm_run([by["docker_cont"]], False)
d = FakeDialog.last
check(d.kw["message_type"] == Gtk.MessageType.WARNING and by["docker_cont"].title in d.secondary, "dangerous task is listed with a warning")
check(d.btns[-1][2].classes == ["destructive-action"] and d.default == CANCEL, "dangerous run: red button, Cancel is default")
w.confirm_run([by["my_root"]], False)
d = FakeDialog.last
check("mine.yaml" in d.secondary and tr("Run them only if you wrote or trust them.") in d.secondary, "own root task: file name and trust warning shown")
check(d.kw["message_type"] == Gtk.MessageType.WARNING, "own root task: warning dialog")
w.confirm_run([by["my_root"]], True)
check(FakeDialog.last.kw["text"] == tr("The preview will run your own tasks as root. Continue?"), "preview of own root task asks too")
FakeDialog.next_response = CANCEL
check(not w.confirm_run([by["thumbs"]], False), "Cancel returns False")

# ---------- start(): dialogs and busy flag ----------
w.estimates = {}
w.sel_ids = lambda: []
FakeDialog.last = None; w.start(False)
check(FakeDialog.last.kw["text"] == tr("Nothing selected") and not w._busy, "nothing selected -> message, nothing starts")
w.sel_ids = lambda: ["thumbs"]
FakeThread.started.clear(); FakeDialog.next_response = CANCEL; w.start(False)
check(not w._busy and not FakeThread.started, "Cancel in the confirmation: nothing starts")
FakeDialog.next_response = OK; w.start(False)
check(w._busy and len(FakeThread.started) == 1 and w._run["ids"] == ["thumbs"], "OK in the confirmation: run starts")
w.set_busy(False); FakeThread.started.clear(); FakeDialog.last = None
w.start(True)
check(FakeDialog.last is None and w._busy and len(FakeThread.started) == 1, "preview of built-in tasks starts without a question")
w.set_busy(False)

# ---------- history: written after a real run ----------
w.free_before = 0; w._rc_bad = False; w.runner.stopped = False
w._run = {"gen": 9, "active": True, "t0": time.monotonic() - 3, "idx": 1, "total": 1, "title": "", "ids": ["thumbs", "tmp"]}
w.finish(False)
rec = history.load()[-1]
check(rec["source"] == "gui" and rec["tasks"] == ["thumbs", "tmp"] and rec["ok"] and rec["seconds"] >= 3, "real run is recorded in the history")
w._rc_bad = True; w._run.update(active=True, t0=time.monotonic()); w.finish(False)
check(history.load()[-1]["ok"] is False, "failed run is recorded as failed")
w._rc_bad = False; w.runner.stopped = True; w._run.update(active=True, t0=time.monotonic()); w.finish(False)
check(history.load()[-1]["stopped"] is True and history.load()[-1]["ok"] is False, "stopped run is recorded as stopped")
w.runner.stopped = False
n_before = len(history.load()); w._run.update(active=True, t0=time.monotonic()); w.finish(True)
check(len(history.load()) == n_before, "a preview is not recorded")

# ---------- history tab ----------
class FakeStore:
    def __init__(self): self.rows = []
    def clear(self): self.rows = []
    def append(self, row): self.rows.append(row)
history.clear()
h = gui.HistoryTab({"tmp": "Temp files"}); h.store = FakeStore(); h.summary = Rec()
h.reload(); check(h.summary.text == tr("No runs recorded yet."), "empty history says so")
history.add(history.make_record("gui", ["tmp"], 2048, 12, True))
history.add(history.make_record("schedule", ["tmp", "x"], 0, 3725, False))
h.reload()
check(len(h.store.rows) == 2 and h.store.rows[0][1] == tr("Scheduled"), "newest run is first")
check(h.store.rows[0][2] == "2" and h.store.rows[0][3] == "01:02:05" and h.store.rows[0][5] == tr("Failed"), "count, HH:MM:SS duration, result")
check(h.store.rows[1][4] == fmt_size(2048) and h.store.rows[1][5] == tr("Success") and "Temp files" in h.store.rows[1][6], "freed size, result and task names in the tooltip")
check("2" in h.summary.text and fmt_size(2048) in h.summary.text, "summary shows runs and total")
FakeDialog.next_response = CANCEL; h.on_clear(); check(len(history.load()) == 2, "Cancel keeps the history")
FakeDialog.next_response = OK; h.on_clear(); check(history.load() == [] and h.summary.text == tr("No runs recorded yet."), "OK clears the history")

# ---------- disk tab: time format ----------
d = gui.DiskTab(); d.progress = Rec(); d._n, d._done, d._cur = 4, 1, "/usr/lib"; d._t0 = time.monotonic() - 3725
d._update_progress(); check(d.progress.text.startswith("25% · 1/4 · 01:02:05 · lib"), "scan time is HH:MM:SS")

# ---------- disk tab: actions ----------
class DModel:
    def __init__(self): self.removed = []
    def remove(self, it): self.removed.append(it)
dm = DModel(); row = ["📁 data", "1.0 KB", 10, "/mnt/data/work", True]
d.status = Rec(); d._selected = lambda: (dm, "IT", row); d._items = [(1000, "/mnt/data/work", True), (5, "/other", False)]
d.act_copy(); check(CLIP.text == "/mnt/data/work" and CLIP.stored and "/mnt/data/work" in d.status.text, "copy path -> clipboard (and stored)")
calls = []
gui.fileops.open_folder = lambda p, isdir: calls.append((p, isdir))
d.act_open(); check(calls == [("/mnt/data/work", True)], "open in file manager gets path and type")
def boom(p, isdir): raise GErr("no handler")
gui.fileops.open_folder = boom; d.act_open(); check("no handler" in d.status.text, "open failure is shown, not raised")
trashed = []
gui.fileops.trash = lambda p: trashed.append(p)
FakeDialog.next_response = CANCEL; d.act_trash(); check(trashed == [] and dm.removed == [], "Cancel: nothing is trashed")
FakeDialog.next_response = OK; d.act_trash()
check(trashed == ["/mnt/data/work"] and dm.removed == ["IT"] and d._items == [(5, "/other", False)], "OK: trashed, row and item removed")
check("work" in d.status.text, "status names the trashed item")
sysrow = ["📁 usr", "1 GB", 50, "/usr", True]; d._selected = lambda: (dm, "IT2", sysrow); trashed.clear(); FakeDialog.next_response = OK
d.act_trash(); check(trashed == [] and "/usr" in d.status.text, "system folders are never trashed")
def failing(p): raise GErr("no trash here")
gui.fileops.trash = failing; d._selected = lambda: (dm, "IT3", row); d.act_trash()
check("no trash here" in d.status.text and "IT3" not in dm.removed, "trash failure is shown, row stays")
def denied(p): raise PermissionError(p)
gui.fileops.trash = denied; d.act_trash(); check("/mnt/data/work" in d.status.text, "PermissionError is handled")
d._selected = lambda: None; d.act_copy(); d.act_open(); d.act_trash(); check(True, "actions without a selection do nothing")
check(d.on_press(Stub(), types.SimpleNamespace(button=1, x=0, y=0)) is False, "left click is left alone")
picked = []
tv = types.SimpleNamespace(get_path_at_pos=lambda x, y: ("PATH", None, 0, 0),
                           get_selection=lambda: types.SimpleNamespace(select_path=lambda p: picked.append(p)))
check(d.on_press(tv, types.SimpleNamespace(button=3, x=5, y=5)) is True and picked == ["PATH"], "right click selects the row and opens the menu")
tv_empty = types.SimpleNamespace(get_path_at_pos=lambda x, y: None)
check(d.on_press(tv_empty, types.SimpleNamespace(button=3, x=5, y=5)) is False, "right click on empty space does nothing")

# ---------- update badge at startup (opt-in) ----------
w.about_btn = Rec()
w._apply_update("0.0.1"); check(w.about_btn.label is None, "older release: no badge")
w._apply_update("9.9.9"); check("9.9.9" in w.about_btn.label and "suggested-action" in w.about_btn.classes and "9.9.9" in w.about_btn.tip, "newer release: button label, accent and tooltip")
w.about_btn = Rec(); FakeThread.started.clear()
updater.check = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network must not be used"))
w.cfg["update_cache"] = {"ts": time.time(), "latest": "9.9.9"}
w.start_update_check(); check("9.9.9" in w.about_btn.label and not FakeThread.started, "fresh cache: badge without network")
w.about_btn = Rec(); w.cfg["update_cache"] = {"ts": time.time() - 13 * 3600, "latest": "9.9.9"}
w.start_update_check(); check(len(FakeThread.started) == 1 and w.about_btn.label is None, "stale cache: a background check starts")
w.cfg["update_cache"] = "garbage"; FakeThread.started.clear(); w.start_update_check(); check(len(FakeThread.started) == 1, "damaged cache is ignored")
res = {"ok": True, "latest": "9.9.9", "url": "https://x/r", "newer": True, "error": ""}
w._update_done(res)
check(json.load(open(settings.path()))["update_cache"]["latest"] == "9.9.9" and "9.9.9" in w.about_btn.label, "result is cached and shown")
before = dict(w.cfg["update_cache"]); w._update_done({"ok": False, "latest": None, "url": None, "newer": False, "error": "offline"})
check(w.cfg["update_cache"] == before, "failed check changes nothing")

# ---------- About dialog logic ----------
ok = lambda **k: dict({"ok": True, "latest": "0.5.0", "url": "https://x/r", "newer": False, "error": ""}, **k)
msg = about.update_message
t, url, lab = msg(ok(), "0.5.0"); check("0.5.0" in t and url is None, "about: up to date")
t, url, lab = msg(ok(latest="0.6.0", newer=True), "0.5.0"); check("0.6.0" in t and url == "https://x/r" and lab, "about: new version with link")
t, url, _l = msg(ok(latest=None), "0.5.0"); check(url is None and t, "about: no releases")
for code in ("offline", "rate_limit", "bad_response", "http_404"):
    t, url, _l = msg({"ok": False, "latest": None, "url": None, "newer": False, "error": code}, "0.5.0")
    check(url is None and t and "{" not in t, f"about: error '{code}' explained")
updater.check = lambda current, **k: ok()
cfg = {}; dlg = about.AboutDialog(None, cfg, lambda: False)
dlg.combo.get_active_id = lambda: "ru"; dlg.on_language(dlg.combo)
check(json.load(open(settings.path()))["language"] == "ru" and cfg["language"] == "ru", "about: language saved")
dlg.on_auto(types.SimpleNamespace(get_active=lambda: True))
check(cfg["check_updates"] is True and json.load(open(settings.path()))["check_updates"] is True, "about: auto-check opt-in saved")
dlg.on_auto(types.SimpleNamespace(get_active=lambda: False)); check(cfg["check_updates"] is False, "about: auto-check switched off")
dlg._show(ok(latest="0.6.0", newer=True)); check(cfg["update_cache"]["latest"] == "0.6.0", "about: a manual check refreshes the cache")
calls = []; dlg.response = lambda r: calls.append(r)
busy = about.AboutDialog(None, {}, lambda: True); busy.response = lambda r: calls.append(r); busy.on_restart(None)
check(calls == [], "about: restart refused while busy")
dlg.on_restart(None); check(calls == [about.RESTART], "about: restart requested when idle")
dlg._alive = False; dlg._show(ok()); check(True, "about: late result after closing is ignored")

# ---------- About: tidy link list ----------
check(about.short_url("https://github.com/agteamdev/syscleaner/") == "github.com/agteamdev/syscleaner"
      and about.short_url("https://www.example.com/a") == "example.com/a", "short_url strips scheme, www and trailing slash")
check(about.update_icon(ok()) == "✅" and about.update_icon(ok(latest="0.6.0", newer=True)) == "🆕"
      and about.update_icon(ok(latest=None)) == "🔎"
      and about.update_icon({"ok": False, "latest": None, "url": None, "newer": False, "error": "offline"}) == "❗", "status icon per state")
from syscleaner import links  # noqa: E402
check(links.APT_URL == "https://github.com/agteamdev/apt", "APT repository link is set")
opened = []
Gio.AppInfo = types.SimpleNamespace(launch_default_for_uri=lambda url, ctx: opened.append(url))
check(about.open_url("https://example.org") is None and opened == ["https://example.org"], "open_url opens the default browser")
def no_browser(url, ctx): raise GErr("no handler")
Gio.AppInfo = types.SimpleNamespace(launch_default_for_uri=no_browser)
check(about.open_url("https://example.org") == "no handler", "open_url returns the error text")
dlg2 = about.AboutDialog(None, {}, lambda: False)
for name in ("msg", "upd_icon", "upd_lbl", "upd_open", "apt_hint", "upd_btn"):
    setattr(dlg2, name, Rec())
dlg2.open_link("https://example.org")
check("no handler" in dlg2.msg.text and dlg2.msg.visible is True, "a link that cannot open is reported in the dialog")
Gio.AppInfo = types.SimpleNamespace(launch_default_for_uri=lambda url, ctx: None)
dlg2.open_link("https://example.org")
check(dlg2.msg.text == "" and dlg2.msg.visible is False, "the message disappears after a successful open")
dlg2._show(ok(latest="0.6.0", newer=True))
check(dlg2.upd_icon.text == "🆕" and dlg2.upd_open.hidden is False and dlg2.apt_hint.hidden is False
      and dlg2._release_url == "https://x/r", "new version: icon, release button and APT hint are shown")
dlg2._show(ok())
check(dlg2.upd_icon.text == "✅" and dlg2.upd_open.hidden is True and dlg2.apt_hint.hidden is True
      and dlg2._release_url is None, "up to date: button and hint are hidden")
dlg2._show({"ok": False, "latest": None, "url": None, "newer": False, "error": "offline"})
check(dlg2.upd_icon.text == "❗" and dlg2.upd_btn.sensitive is True, "offline: error icon, retry possible")

print(f"\nGUI smoke OK ({n} checks) | lang={tr('Select all')}")
