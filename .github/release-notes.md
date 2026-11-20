## SysCleaner 0.2.0

A graphical cleanup and diagnostics tool for **Linux Mint / Debian / Ubuntu**, built from a hand-tuned cleanup checklist: pick what to clean, read what each task does and how risky it is, preview the result, then run it and watch the live log.

### Highlights

- 🧹 **30 ready-made tasks** in three groups: cleanup, find junk, diagnostics & security.
- 🟢🟡🔴 **Risk levels and explanations** for every task; dangerous ones need confirmation and can never be scheduled.
- 🔍 **Preview (dry-run)**: shows what would be affected and a per-task and total **size estimate** before anything is deleted.
- 📜 **Live log** with colour-coded output and a "freed space" summary.
- 📊 **Disk tab**: ncdu-style browser, double-click to drill down, bars show the share of the parent folder, optional "as root" scan.
- ⏱ **Scheduling** through a **systemd timer** (daily / weekly / monthly). Logs: `journalctl -u syscleaner`.
- 📝 **Tasks live in YAML**: add your own in `~/.config/syscleaner/tasks.d/*.yaml` without touching the code, or hide built-in ones.
- 🔐 One password prompt per run (polkit / `pkexec`), no `sudo` inside the GUI.
- 🌗 **Follows your system**: light/dark GTK theme and system language (English and Russian included; adding a language is one YAML file).
- 💻 CLI / headless mode: `syscleaner --list`, `syscleaner --headless --dry-run --tasks tmp,thumbs`.

### Safe by design

SysCleaner deliberately does **not** run `rm -rf /tmp/*`, `rm -rf ~/.cache/*`, `docker system prune -a --volumes`, manual kernel removal or log truncation.

### Downloads

| File | For |
|---|---|
| `syscleaner_0.2.0_all.deb` | Linux Mint / Debian / Ubuntu: `sudo apt install ./syscleaner_0.2.0_all.deb` |
| `SysCleaner-0.2.0-x86_64.AppImage` | Any distro with `python3-gi` + GTK3: `chmod +x` and run |

### Requirements

Python 3, `python3-gi`, GTK 3 (`gir1.2-gtk-3.0`), `python3-yaml`, polkit (`pkexec`). All are preinstalled on a standard Linux Mint desktop except possibly `python3-yaml`.

### Notes

- The AppImage uses the system GTK/PyGObject. If you enable the schedule from an AppImage, do not move the file afterwards.
- Size estimates are approximate; some tasks (Docker, Flatpak) show `n/a`.
- Early release: feedback and issues are very welcome.
