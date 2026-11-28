SysCleaner is a graphical cleanup and diagnostics tool for Linux Mint, Debian and Ubuntu. Pick tasks, read what each one does and how risky it is, preview the result with size estimates, then run it and follow the live log.

## Features

- System and package cleanup: APT, Snap, DNF, Pacman and Zypper caches, old kernels, logs, crash reports, core dumps, Flatpak, thumbnails, trash
- Browsers: Firefox, Chrome, Chromium, Edge, Brave, Vivaldi and Opera (regular, Snap and Flatpak installs); only caches are removed, never profiles or passwords, and a running browser is skipped
- Developer tools: npm, pip, pnpm, Yarn, Cargo, Gradle, Go and Docker
- Only tasks that apply to your system are shown
- Risk levels (safe / caution / dangerous) with an explanation for every task; dangerous tasks ask for confirmation and are never scheduled
- Preview (dry-run) with per-task and total size estimates; nothing is deleted
- Live log with a summary of freed space, plus a run history (manual, scheduled and command-line runs)
- Disk tab: ncdu-style browser with scan progress, drill-down, an optional scan as root, and actions: open in file manager, copy path, move to trash
- Scheduling with a systemd timer (daily, weekly, monthly) with "Run now" and the result of the last run; logs via `journalctl -u syscleaner`
- Your own tasks in YAML (`~/.config/syscleaner/tasks.d/`), no code changes needed
- Follows the system light/dark theme and language (English, Russian, Ukrainian, Italian, German, Spanish, French, Polish and Portuguese included); the language can also be chosen manually
- Remembers the window size, position and panel split between runs
- Progress bar with percent and elapsed time while scanning and cleaning
- About dialog: version, update check (optional automatic check at startup), links to the issue tracker, ways to support the project
- A confirmation with a size estimate before every run; your own root tasks are marked and always confirmed
- One password prompt per run (polkit / pkexec)
- CLI / headless mode: `syscleaner --list`, `syscleaner --headless --dry-run --tasks tmp,thumbs`

SysCleaner deliberately does not run `rm -rf /tmp/*`, `rm -rf ~/.cache/*`, `docker system prune -a --volumes`, manual kernel removal or log truncation.

## Downloads

| File | Use with |
|---|---|
| APT repository | Debian 12+, Ubuntu 22.04+, Linux Mint 21+: [instructions](https://github.com/agteamdev/apt); updates arrive with `apt upgrade` |
| `syscleaner_<version>_all.deb` | Linux Mint / Debian / Ubuntu: `sudo apt install ./syscleaner_*_all.deb` |
| `SysCleaner-<version>-x86_64.AppImage` | Any distro with `python3-gi` and GTK 3: `chmod +x SysCleaner-*.AppImage && ./SysCleaner-*.AppImage` |

## Requirements

Python 3, `python3-gi`, GTK 3 (`gir1.2-gtk-3.0`), `python3-yaml` and polkit (`pkexec`).

## Notes

- The AppImage uses the system GTK / PyGObject. If you enable the schedule from an AppImage, do not move the file afterwards.
- Built for Debian-based systems. The DNF, Pacman and Zypper tasks are included but not yet tested on those distributions.
- Size estimates are approximate; some tasks (Docker, Pacman, Zypper) show `n/a`.
