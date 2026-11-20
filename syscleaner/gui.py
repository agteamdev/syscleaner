"""GTK3-интерфейс SysCleaner."""
from __future__ import annotations

import os
import pwd
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from . import __version__, schedule  # noqa: E402
from .runner import EST_RE, Runner, build_script, fmt_size  # noqa: E402
from .tasks import available, load  # noqa: E402

RISK = {"safe": "🟢 безопасно", "caution": "🟡 внимание", "danger": "🔴 опасно"}
ERR_RE = re.compile(r"(?i)(\berror\b|ошибка|\bfailed\b|permission denied|^E: )")


def _msg(parent, kind, text, secondary=None, buttons=Gtk.ButtonsType.OK):
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind, buttons=buttons, text=text)
    if secondary:
        d.format_secondary_text(secondary)
    r = d.run()
    d.destroy()
    return r


# ───────────────────────── вкладка «Диск» ─────────────────────────
class DiskTab(Gtk.Box):
    """ncdu-подобный просмотр: двойной клик — зайти в папку, полоса — доля от родителя."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(4)
        top = Gtk.Box(spacing=6)
        self.entry = Gtk.Entry(text=str(Path.home()), hexpand=True)
        self.entry.connect("activate", lambda *_: self.scan(self.entry.get_text()))
        for label, fn in (("⬆ Вверх", lambda *_: self.scan(os.path.dirname(self.cur.rstrip("/")) or "/")),
                          ("🏠 ~", lambda *_: self.scan(str(Path.home()))),
                          ("/", lambda *_: self.scan("/"))):
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            top.pack_start(b, False, False, 0)
        top.pack_start(self.entry, True, True, 0)
        self.chk_root = Gtk.CheckButton(label="от root")
        self.chk_root.set_tooltip_text("Видеть и системные папки без прав доступа (запросит пароль)")
        top.pack_start(self.chk_root, False, False, 0)
        go = Gtk.Button(label="Сканировать")
        go.connect("clicked", lambda *_: self.scan(self.entry.get_text()))
        top.pack_start(go, False, False, 0)
        self.pack_start(top, False, False, 0)

        self.cur = str(Path.home())
        self.store = Gtk.ListStore(str, str, int, str, bool)  # имя, размер, %, путь, папка?
        tv = Gtk.TreeView(model=self.store)
        c1 = Gtk.TreeViewColumn("Имя", Gtk.CellRendererText(), text=0)
        c1.set_expand(True)
        tv.append_column(c1)
        c2 = Gtk.TreeViewColumn("Доля от папки", Gtk.CellRendererProgress(), value=2, text=1)
        c2.set_min_width(300)
        tv.append_column(c2)
        tv.connect("row-activated", self.on_activate)
        sw = Gtk.ScrolledWindow()
        sw.add(tv)
        self.pack_start(sw, True, True, 0)
        self.status = Gtk.Label(xalign=0, label="Нажми «Сканировать». Двойной клик по папке — зайти внутрь.")
        self.pack_start(self.status, False, False, 0)

    def on_activate(self, tv, path, _col):
        row = self.store[path]
        if row[4]:
            self.scan(row[3])

    def scan(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            self.status.set_text(f"Не папка: {path}")
            return
        self.cur = path
        self.entry.set_text(path)
        self.store.clear()
        self.status.set_text("⏳ Сканирование… (на больших разделах может занять минуту)")
        threading.Thread(target=self._scan, args=(path, self.chk_root.get_active()), daemon=True).start()

    def _scan(self, path, as_root):
        argv = ["du", "-xa", "-B1", "--max-depth=1", path]
        if as_root:
            argv.insert(0, "pkexec")
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace")
        rows, total = [], 0
        for line in p.stdout.splitlines():
            try:
                size, pp = line.split("\t", 1)
                size = int(size)
            except ValueError:
                continue
            if pp == path:
                total = size
            else:
                rows.append((size, pp))
        rows.sort(reverse=True)
        out = [(size, pp, os.path.isdir(pp) and not os.path.islink(pp)) for size, pp in rows[:500]]
        GLib.idle_add(self._fill, path, total, out)

    def _fill(self, path, total, rows):
        if path != self.cur:
            return
        for size, pp, isdir in rows:
            pct = int(100 * size / total) if total else 0
            self.store.append([("📁 " if isdir else "📄 ") + os.path.basename(pp), fmt_size(size),
                               min(pct, 100), pp, isdir])
        self.status.set_text(f"{path} — всего {fmt_size(total)}, элементов: {len(rows)} (только этот раздел, -x)")


# ───────────────────────── главное окно ─────────────────────────
class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=f"SysCleaner {__version__}")
        self.set_default_size(1200, 780)
        self.set_icon_name("syscleaner")
        icon = Path(__file__).resolve().parent.parent / "packaging" / "syscleaner.svg"
        if icon.exists():
            try:
                self.set_icon_from_file(str(icon))
            except Exception:  # noqa: BLE001
                pass
        self.groups, self.tasks, self.warnings = load()
        self.by_id = {t.id: t for t in self.tasks}
        self.estimates: dict = {}
        self.runner = Runner()
        self.free_before = 0

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(8)
        self.add(outer)
        self.disk_lbl = Gtk.Label(xalign=0)
        self.disk_bar = Gtk.ProgressBar()
        outer.pack_start(self.disk_lbl, False, False, 0)
        outer.pack_start(self.disk_bar, False, False, 0)
        nb = Gtk.Notebook()
        outer.pack_start(nb, True, True, 0)
        nb.append_page(self._clean_tab(), Gtk.Label(label="🧹 Очистка"))
        nb.append_page(DiskTab(), Gtk.Label(label="📊 Диск"))
        self.update_disk()
        for w in self.warnings:
            self.write(f"⚠ {w}\n", "err")

    # ---- вкладка очистки ----
    def _clean_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.set_border_width(4)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        page.pack_start(paned, True, True, 0)

        # active, markup, id, sensitive, risk, size
        self.store = Gtk.TreeStore(bool, str, str, bool, str, str)
        parents = {}
        for gid, gtitle in self.groups:
            parents[gid] = self.store.append(None, [False, f"<b>{GLib.markup_escape_text(gtitle)}</b>", "", True, "", ""])
        for t in self.tasks:
            ok = available(t)
            label = GLib.markup_escape_text(t.title) + (" ⏱" if t.schedule else "")
            if not ok:
                label += f"  <i>(нет {GLib.markup_escape_text(t.requires)})</i>"
            self.store.append(parents[t.group], [t.default and ok, label, t.id, ok, RISK[t.risk], ""])

        tv = Gtk.TreeView(model=self.store)
        tv.set_headers_visible(False)
        tg = Gtk.CellRendererToggle()
        tg.connect("toggled", self.on_toggle)
        tv.append_column(Gtk.TreeViewColumn("", tg, active=0, sensitive=3))
        c = Gtk.TreeViewColumn("Задача", Gtk.CellRendererText(), markup=1, sensitive=3)
        c.set_expand(True)
        tv.append_column(c)
        rs = Gtk.CellRendererText(xalign=1.0)
        tv.append_column(Gtk.TreeViewColumn("Размер", rs, text=5))
        tv.append_column(Gtk.TreeViewColumn("Риск", Gtk.CellRendererText(), text=4))
        tv.expand_all()
        tv.get_selection().connect("changed", self.on_select)
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_width(560)
        sw.add(tv)
        paned.pack1(sw, True, False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.desc = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True)
        self.desc.set_markup("<i>Выбери задачу слева — здесь появятся описание и команда.\n"
                             "⏱ — задачу можно поставить в расписание. Кнопка «Предпросмотр» "
                             "ничего не удаляет и показывает оценку размера.</i>")
        right.pack_start(self.desc, False, False, 0)
        self.total_lbl = Gtk.Label(xalign=0)
        right.pack_start(self.total_lbl, False, False, 0)
        self.log = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        buf = self.log.get_buffer()
        buf.create_tag("head", weight=Pango.Weight.BOLD, foreground="#2a7ae4")
        buf.create_tag("err", foreground="#d33")
        buf.create_tag("ok", foreground="#2a9d4a")
        buf.create_mark("end", buf.get_end_iter(), False)
        lsw = Gtk.ScrolledWindow()
        lsw.add(self.log)
        right.pack_start(lsw, True, True, 0)
        paned.pack2(right, True, False)
        paned.set_position(600)

        bar = Gtk.Box(spacing=6)
        for text, fn in (("Только безопасные", self.sel_safe), ("Снять всё", self.sel_none),
                         ("Очистить лог", lambda *_: buf.set_text(""))):
            b = Gtk.Button(label=text)
            b.connect("clicked", fn)
            bar.pack_start(b, False, False, 0)
        self.btn_sched = Gtk.Button(label="⏱ Расписание…")
        self.btn_sched.connect("clicked", self.on_schedule)
        self.btn_dry = Gtk.Button(label="🔍 Предпросмотр")
        self.btn_dry.connect("clicked", lambda *_: self.start(True))
        self.btn_run = Gtk.Button(label="▶ Запустить выбранное")
        self.btn_run.get_style_context().add_class("suggested-action")
        self.btn_run.connect("clicked", lambda *_: self.start(False))
        self.btn_stop = Gtk.Button(label="■ Стоп", sensitive=False)
        self.btn_stop.connect("clicked", lambda *_: self.runner.stop())
        for b in (self.btn_run, self.btn_dry, self.btn_sched):
            bar.pack_end(b, False, False, 0)
        bar.pack_end(self.btn_stop, False, False, 0)
        page.pack_start(bar, False, False, 0)
        return page

    # ---- утилиты ----
    def update_disk(self):
        u = shutil.disk_usage("/")
        self.disk_lbl.set_markup(f"Диск <b>/</b>: занято <b>{u.used / 2**30:.1f}</b> ГБ из "
                                 f"{u.total / 2**30:.1f}, свободно <b>{u.free / 2**30:.1f}</b> ГБ")
        self.disk_bar.set_fraction(u.used / u.total)
        return u.free

    def write(self, text, tag=None):
        buf = self.log.get_buffer()
        if tag is None:
            if ERR_RE.search(text):
                tag = "err"
            elif text.startswith("▶") or text.startswith("==="):
                tag = "head"
        if tag:
            buf.insert_with_tags_by_name(buf.get_end_iter(), text, tag)
        else:
            buf.insert(buf.get_end_iter(), text)
        mark = buf.get_mark("end")
        buf.move_mark(mark, buf.get_end_iter())
        self.log.scroll_mark_onscreen(mark)

    def sel_ids(self):
        return [ch[2] for grp in self.store for ch in grp.iterchildren() if ch[0] and ch[3]]

    def on_toggle(self, _r, path):
        row = self.store[path]
        if not row[3]:
            return
        row[0] = not row[0]
        if row[2] == "":
            for ch in row.iterchildren():
                if ch[3]:
                    ch[0] = row[0]
        self.update_total()

    def on_select(self, sel):
        model, it = sel.get_selected()
        if not it or not model[it][2]:
            return
        t = self.by_id[model[it][2]]
        esc = GLib.markup_escape_text
        extra = ""
        if t.preview or t.estimate:
            extra = "\n\n<small>Для предпросмотра: " + esc((t.estimate or t.preview).splitlines()[0]) + "</small>"
        self.desc.set_markup(
            f"<big><b>{esc(t.title)}</b></big>\n"
            f"Риск: {RISK[t.risk]}  ·  {'нужен root (запросит пароль)' if t.root else 'без root'}"
            f"{'  ·  можно по расписанию ⏱' if t.schedule else ''}\n\n"
            f"{esc(t.desc)}\n\n<tt>{esc(('sudo ' if t.root else '') + t.cmd)}</tt>{extra}")

    def sel_safe(self, *_):
        for grp in self.store:
            grp[0] = False
            for ch in grp.iterchildren():
                t = self.by_id[ch[2]]
                ch[0] = ch[3] and t.risk == "safe" and t.group == "clean"
        self.update_total()

    def sel_none(self, *_):
        for grp in self.store:
            grp[0] = False
            for ch in grp.iterchildren():
                ch[0] = False
        self.update_total()

    def update_total(self):
        ids = [i for i in self.sel_ids() if self.estimates.get(i)]
        if not self.estimates:
            self.total_lbl.set_text("")
            return
        tot = sum(self.estimates[i] for i in ids)
        self.total_lbl.set_markup(f"Оценка к освобождению по выбранным: <b>{fmt_size(tot)}</b> (приблизительно)")

    def refresh_sizes(self):
        for grp in self.store:
            s, have = 0, False
            for ch in grp.iterchildren():
                if ch[2] in self.estimates:
                    v = self.estimates[ch[2]]
                    ch[5] = "н/д" if v is None else fmt_size(v)
                    if v:
                        s += v
                        have = True
                else:
                    ch[5] = ""
            grp[5] = fmt_size(s) if have else ""
        self.update_total()

    def set_busy(self, busy):
        for b in (self.btn_run, self.btn_dry, self.btn_sched):
            b.set_sensitive(not busy)
        self.btn_stop.set_sensitive(busy)

    # ---- запуск / предпросмотр ----
    def handle_line(self, line):
        m = EST_RE.match(line)
        if m:
            v = None if m.group(2) == "-" else int(m.group(2))
            GLib.idle_add(self._set_est, m.group(1), v)
        else:
            GLib.idle_add(self.write, line + "\n")

    def _set_est(self, tid, v):
        self.estimates[tid] = v
        t = self.by_id.get(tid)
        self.write(f"   оценка: {'н/д' if v is None else fmt_size(v)}\n", "ok")
        return False

    def start(self, dry):
        ids = self.sel_ids()
        if not ids:
            _msg(self, Gtk.MessageType.INFO, "Ничего не выбрано")
            return
        tasks = [self.by_id[i] for i in ids]
        risky = [t for t in tasks if t.risk == "danger"]
        if risky and not dry:
            r = _msg(self, Gtk.MessageType.WARNING, "Выбраны опасные задачи",
                     "\n".join("• " + t.title for t in risky) + "\n\nСначала сделай «Предпросмотр». Продолжить?",
                     Gtk.ButtonsType.OK_CANCEL)
            if r != Gtk.ResponseType.OK:
                return
        self.set_busy(True)
        self.runner.stopped = False
        self.free_before = self.update_disk()
        self.write(f"\n=== {'ПРЕДПРОСМОТР (ничего не удаляется)' if dry else 'ЗАПУСК'} · "
                   f"{datetime.now():%H:%M:%S} ===\n", "head")
        threading.Thread(target=self.worker, args=(tasks, dry), daemon=True).start()

    def worker(self, tasks, dry):
        try:
            rt = [t for t in tasks if t.root]
            ut = [t for t in tasks if not t.root]
            if rt:
                GLib.idle_add(self.write, "━━ root-задачи (один запрос пароля) ━━\n", "head")
                rc = self.runner.stream(["pkexec", "bash", "-c", build_script(rt, dry)], self.handle_line)
                GLib.idle_add(self.write, f"[код возврата: {rc}]\n", "ok" if rc == 0 else "err")
            if ut and not self.runner.stopped:
                GLib.idle_add(self.write, "━━ пользовательские задачи ━━\n", "head")
                rc = self.runner.stream(["bash", "-c", build_script(ut, dry)], self.handle_line)
                GLib.idle_add(self.write, f"[код возврата: {rc}]\n", "ok" if rc == 0 else "err")
        except Exception as e:  # noqa: BLE001
            GLib.idle_add(self.write, f"Ошибка запуска: {e}\n", "err")
        finally:
            GLib.idle_add(self.finish, dry)

    def finish(self, dry):
        free = self.update_disk()
        if dry:
            self.refresh_sizes()
            sel = [self.estimates.get(i) or 0 for i in self.sel_ids()]
            self.write(f"\n✔ Предпросмотр завершён. Можно освободить ≈ {fmt_size(sum(sel))}\n", "ok")
        else:
            self.write(f"\n✔ Готово. Свободного места стало больше на {fmt_size(max(0, free - self.free_before))}\n", "ok")
            self.estimates.clear()
            self.refresh_sizes()
        self.set_busy(False)

    # ---- расписание ----
    def on_schedule(self, _b):
        ids = [i for i in self.sel_ids() if self.by_id[i].schedule]
        dlg = Gtk.Dialog(title="Расписание очистки (systemd timer)", transient_for=self, modal=True)
        dlg.add_button("Закрыть", Gtk.ResponseType.CLOSE)
        dlg.add_button("Отключить расписание", 2)
        dlg.add_button("Включить / обновить", 1)
        area = dlg.get_content_area()
        area.set_spacing(8)
        area.set_border_width(12)
        area.pack_start(Gtk.Label(xalign=0, label=f"Статус: {schedule.status()}"), False, False, 0)
        names = "\n".join("  • " + self.by_id[i].title for i in ids) or "  (нет — отметь в списке задачи с значком ⏱)"
        area.pack_start(Gtk.Label(xalign=0, label="Будут запускаться отмеченные задачи с ⏱:\n" + names), False, False, 0)
        combo = Gtk.ComboBoxText()
        for k in schedule.FREQS:
            combo.append_text(k)
        combo.set_active(1)
        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label="Периодичность:"), False, False, 0)
        row.pack_start(combo, False, False, 0)
        row.pack_start(Gtk.Label(label="время (ЧЧ:ММ):"), False, False, 0)
        tm = Gtk.Entry(text="04:30", width_chars=6)
        row.pack_start(tm, False, False, 0)
        area.pack_start(row, False, False, 0)
        area.pack_start(Gtk.Label(xalign=0, wrap=True, label=(
            "Запуск от root через systemd (ночью, с низким приоритетом); журнал: "
            "journalctl -u syscleaner. Опасные задачи в расписание не попадают.")), False, False, 0)
        dlg.show_all()
        resp = dlg.run()
        freq, hhmm = combo.get_active_text(), tm.get_text().strip()
        dlg.destroy()
        if resp == 1:
            if not ids:
                _msg(self, Gtk.MessageType.INFO, "Нет задач для расписания")
                return
            if not schedule.TIME_RE.match(hhmm):
                _msg(self, Gtk.MessageType.ERROR, "Время должно быть в формате ЧЧ:ММ")
                return
            user = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
            self.run_root_script(schedule.install_script(ids, freq, hhmm.zfill(5), user), "Включение расписания")
        elif resp == 2:
            self.run_root_script(schedule.uninstall_script(), "Отключение расписания")

    def run_root_script(self, script, title):
        self.set_busy(True)
        self.runner.stopped = False
        self.write(f"\n=== {title} ===\n", "head")

        def w():
            try:
                rc = self.runner.stream(["pkexec", "bash", "-c", script], self.handle_line)
                GLib.idle_add(self.write, f"[код возврата: {rc}]\n", "ok" if rc == 0 else "err")
            finally:
                GLib.idle_add(self.set_busy, False)
        threading.Thread(target=w, daemon=True).start()


def run():
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
