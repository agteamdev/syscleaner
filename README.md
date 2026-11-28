<p align="center">
  <img src="packaging/icons/256x256/syscleaner.png" width="128" alt="SysCleaner icon">
</p>

<h1 align="center">SysCleaner</h1>

<p align="center">GUI cleanup and diagnostics for <b>Linux Mint / Debian / Ubuntu</b> (GTK3 + Python)</p>

![SysCleaner](docs/screenshots/cleanup.png)

Pick tasks with checkboxes, read what each one does and how risky it is, preview the result with size estimates, run it and watch a live log.

## Features

- **System and package cleanup**: APT, Snap, DNF, Pacman and Zypper caches, old kernels, logs, crash reports, core dumps, Flatpak, thumbnails, trash.
- **Browsers**: Firefox, Chrome, Chromium, Edge, Brave, Vivaldi and Opera (regular, Snap and Flatpak installs). Only caches are removed, never profiles, passwords or bookmarks, and a running browser is skipped.
- **Developer tools**: npm, pip, pnpm, Yarn, Cargo, Gradle, Go and Docker.
- **Only what applies to your system is shown**: missing browsers, package managers and tools are hidden.
- **Tasks with explanations and risk levels**: 🟢 safe · 🟡 caution · 🔴 dangerous (dangerous tasks ask for confirmation).
- **Preview (dry-run)**: deletes nothing; shows what would be affected and a size estimate per task and in total.
- **Live log** of every command, plus a "freed space" summary, and a **run history** (manual, scheduled and command-line runs).
- **Progress** with percent and elapsed time (00:00:00) while scanning and cleaning.
- **Disk tab**: ncdu-style browser with *Open in file manager*, *Copy path* and *Move to trash*; double-click to drill down, bars show the share of the parent folder, optional scan as root.
- **Scheduling** via systemd timer (daily / weekly / monthly) with *Run now* and the last run's result; logs: `journalctl -u syscleaner`.
- **Tasks in YAML**: add your own without changing the code.
- **One password prompt** for all root tasks (polkit / `pkexec`), and a confirmation with a size estimate before anything runs.
- **Follows your system**: light/dark theme and language (English, Russian, Ukrainian, Italian, German, Spanish, French, Polish and Portuguese included), with a manual language choice.
- **Remembers the window**: size, position and panel split are restored on the next start.
- **About dialog**: version, update check (optional automatic check at startup) with a link to the new release, issue tracker and ways to support the project.
- **Headless / CLI mode** for scripts and the scheduler.

## Install

### APT repository (recommended)

Debian 12+, Ubuntu 22.04+, Linux Mint 21+. Updates arrive together with the rest of your system.

```bash
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://apt.alexgor.com/key.asc -o /etc/apt/keyrings/agteamdev.asc
sudo curl -fsSL https://apt.alexgor.com/agteamdev.sources -o /etc/apt/sources.list.d/agteamdev.sources
sudo apt update
sudo apt install syscleaner
```

The signed repository lives at [agteamdev/apt](https://github.com/agteamdev/apt). Later versions: `sudo apt update && sudo apt upgrade`.

### Other ways

Download a `.deb` or `.AppImage` from the [Releases page](https://github.com/agteamdev/syscleaner/releases/latest), or run from source:

```bash
# .deb (Linux Mint / Debian / Ubuntu)
sudo apt install ./syscleaner_*_all.deb

# AppImage (any distro with python3-gi and GTK3)
chmod +x SysCleaner-*.AppImage && ./SysCleaner-*.AppImage

# from source
git clone https://github.com/agteamdev/syscleaner.git && cd syscleaner
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml policykit-1
python3 -m syscleaner
```

> Built for Debian-based systems. The DNF, Pacman and Zypper tasks are included but not yet tested on those distributions.
>
> The AppImage uses the system `python3-gi` / GTK3 (preinstalled on Mint, Ubuntu and Debian desktops).
> If you enable the schedule from an AppImage, don't move the file afterwards: the timer points to its path.

## Usage

Start **SysCleaner** from the application menu, or from a terminal:

```bash
syscleaner                                           # GUI
syscleaner --list                                    # list tasks
syscleaner --headless --dry-run --tasks tmp,thumbs   # preview without a GUI
sudo syscleaner --headless --tasks apt_clean,tmp --user "$USER"
```

## Custom tasks (YAML)

Built-in tasks live in `syscleaner/data/tasks.yaml`. Add yours to `~/.config/syscleaner/tasks.d/*.yaml`:

```yaml
groups:
  - {id: mine, title: "⭐ Mine"}
tasks:
  - id: my_cache
    group: mine                      # a group id
    title: "My app cache"
    desc: What it does and what it risks
    cmd: rm -rf ~/.cache/myapp/*     # with root: true write it without sudo
    risk: safe                       # safe | caution | danger
    estimate: sz ~/.cache/myapp      # prints bytes; sz = total size of paths
    preview: ls -la ~/.cache/myapp | head
  - id: brave                        # hide a built-in task
    disabled: true
```

Your own tasks are marked *(custom)*; those that run as root also get a ⚠ and always ask for confirmation. They can't be scheduled, because the schedule runs as root and only knows the built-in tasks.

Other fields: `root`, `default`, `requires` (a program that must exist), `requires_path` (folders that must exist, `~` and `*` allowed) and `hide_missing` (hide the task instead of greying it out when those are missing). YAML errors are shown as warnings in the log.

## Language and theme

- **Theme**: SysCleaner is a plain GTK3 app, so it uses your current system theme (light or dark).
- **Language**: pick one in **About** (applies after a restart), or leave it on *System default* (detected from `LANGUAGE` / `LC_ALL` / `LANG`). `SYSCLEANER_LANG=en syscleaner` overrides both. Settings are stored in `~/.config/syscleaner/settings.json`.
- **Add a language**: copy `syscleaner/data/i18n/ru.yaml` to `<lang>.yaml`, translate the values (keys stay in English), set `meta.name` to the language's own name, and run `python3 tools/check_i18n.py`. The new language then appears in the picker.

## Build from source

```bash
make check      # compile + validate YAML + check translations
make test       # unit tests
make deb        # dist/syscleaner_<version>_all.deb
make appimage   # dist/SysCleaner-<version>-x86_64.AppImage
```

## Safety

Deliberately **not** included: `rm -rf /tmp/*`, `rm -rf ~/.cache/*`, `docker system prune -a --volumes`, manual kernel removal and log truncation. Dangerous tasks are never scheduled.

## License

MIT
