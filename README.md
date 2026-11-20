<p align="center">
  <img src="packaging/icons/256x256/syscleaner.png" width="128" alt="SysCleaner icon">
</p>

<h1 align="center">SysCleaner</h1>

**GUI cleanup and diagnostics for Linux Mint / Debian / Ubuntu** (GTK3 + Python).

Pick tasks with checkboxes, read what each one does and how risky it is, preview the result with size estimates, run it and watch a live log. Includes an ncdu-style disk browser and scheduling via systemd timer.

## Features

- **Tasks with explanations and risk levels**: 🟢 safe · 🟡 caution · 🔴 dangerous (dangerous tasks ask for confirmation).
- **Preview (dry-run)**: deletes nothing; shows what would be affected and a size estimate per task and in total.
- **Live log** of every command, plus a "freed space" summary.
- **Disk tab**: browse folders, double-click to drill down, bars show the share of the parent; optional scan as root.
- **Scheduling**: systemd timer (daily / weekly / monthly); logs via `journalctl -u syscleaner`.
- **Tasks in YAML**: add your own without changing the code.
- **One password prompt** for all root tasks (polkit / `pkexec`).
- **Headless / CLI mode** for scripts and the scheduler.
- **Follows your system**: light/dark GTK theme and system language (English and Russian included; more are one YAML file away).

## Screenshots

| Cleanup | Preview (dry-run) | Disk |
|---|---|---|
| ![Cleanup](docs/screenshots/cleanup.png) | ![Preview](docs/screenshots/preview.png) | ![Disk](docs/screenshots/disk.png) |

## Install

```bash
# .deb (recommended)
sudo apt install ./syscleaner_0.2.0_all.deb

# AppImage
chmod +x SysCleaner-0.2.0-x86_64.AppImage && ./SysCleaner-0.2.0-x86_64.AppImage

# from source
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml policykit-1
python3 -m syscleaner
```

> The AppImage uses the system `python3-gi` / GTK3 (preinstalled on Mint, Ubuntu and Debian desktops).
> If you enable the schedule from an AppImage, don't move the file afterwards: the timer points to its path.

## CLI

```bash
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
    schedule: true                   # may be scheduled (never for danger)
  - id: brave                        # hide a built-in task
    disabled: true
```

Other fields: `root`, `default`, `requires` (a program that must exist, otherwise the task is greyed out). YAML errors are shown as warnings in the log.

## Language and theme

- **Theme**: SysCleaner is a plain GTK3 app, so it uses your current system theme (light or dark). Log colours adapt automatically.
- **Language**: detected from `LANGUAGE` / `LC_ALL` / `LANG`. Force one with `SYSCLEANER_LANG=en syscleaner`.
- **Add a language**: copy `syscleaner/data/i18n/ru.yaml` to `<lang>.yaml`, translate the values (keys stay in English), then run `python3 tools/check_i18n.py`. Personal tweaks without touching the repo go to `~/.config/syscleaner/i18n/<lang>.yaml`.

## Build

```bash
make check      # compile + validate YAML + check translations
make deb        # dist/syscleaner_<ver>_all.deb
make appimage   # dist/SysCleaner-<ver>-x86_64.AppImage (needs internet for appimagetool)
make screenshots  # refresh docs/screenshots/*.png (run inside a desktop session)
```

For light/dark screenshots: `SYSCLEANER_LANG=en GTK_THEME=Adwaita:dark python3 tools/screenshots.py dark` (and `GTK_THEME=Adwaita ... light`).

Pushing a tag builds both packages on GitHub Actions and attaches them to a release:

```bash
git tag v0.2.0 && git push origin v0.2.0
```

## Safety

Deliberately **not** included: `rm -rf /tmp/*`, `rm -rf ~/.cache/*`, `docker system prune -a --volumes`, manual kernel removal and log truncation. Dangerous tasks are never scheduled.

## License

MIT
