A graphical cleanup and diagnostics tool for **Linux Mint / Debian / Ubuntu**: pick what to clean, read what each task does and how risky it is, preview the result, then run it and watch the live log.

### Highlights

- 🧹 **30 ready-made tasks** in three groups: cleanup, find junk, diagnostics & security.
- 🟢🟡🔴 **Risk levels and explanations** for every task; dangerous ones need confirmation and can never be scheduled.
- 🔍 **Preview (dry-run)** with per-task and total **size estimates** before anything is deleted.
- 📜 **Live log** with colour-coded output and a "freed space" summary.
- 📊 **Disk tab**: ncdu-style browser with scan progress, drill-down and optional "as root" scan.
- ⏱ **Scheduling** through a **systemd timer** (daily / weekly / monthly). Logs: `journalctl -u syscleaner`.
- 📝 **Tasks live in YAML**: add your own in `~/.config/syscleaner/tasks.d/*.yaml` without touching the code.
- 🌗 **Follows your system**: light/dark GTK theme and system language (English and Russian included).
- 🔐 One password prompt per run (polkit / `pkexec`).
- 💻 CLI / headless mode: `syscleaner --list`, `syscleaner --headless --dry-run --tasks tmp,thumbs`.

### Safe by design

SysCleaner deliberately does **not** run `rm -rf /tmp/*`, `rm -rf ~/.cache/*`, `docker system prune -a --volumes`, manual kernel removal or log truncation.

### Downloads

| File | For |
|---|---|
| `syscleaner_<version>_all.deb` | Linux Mint / Debian / Ubuntu: `sudo apt install ./syscleaner_*_all.deb` |
| `SysCleaner-<version>-x86_64.AppImage` | Any distro with `python3-gi` + GTK3: `chmod +x` and run |

### Requirements

Python 3, `python3-gi`, GTK 3 (`gir1.2-gtk-3.0`), `python3-yaml`, polkit (`pkexec`).

### Notes

- The AppImage uses the system GTK/PyGObject. If you enable the schedule from an AppImage, do not move the file afterwards.
- Size estimates are approximate; some tasks (Docker, Flatpak) show `n/a`.
