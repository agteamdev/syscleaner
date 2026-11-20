# SysCleaner

GUI-очистка и диагностика для **Linux Mint / Debian / Ubuntu** (GTK3 + Python).
Выбор задач галочками, объяснение и уровень риска у каждой, предпросмотр с оценкой размера,
лог выполнения в реальном времени, ncdu-подобный просмотр диска и расписание через systemd timer.

## Возможности

- **Задачи с описаниями и риском** 🟢 безопасно · 🟡 внимание · 🔴 опасно (опасные требуют подтверждения).
- **Предпросмотр (dry-run)** — ничего не удаляет, показывает что будет затронуто и оценку размера по каждой задаче и в сумме.
- **Лог в реальном времени**, итог «освободилось X».
- **Вкладка «Диск»** — навигация по папкам, полосы долей от родителя, режим «от root».
- **Расписание** — systemd timer (ежедневно / еженедельно / ежемесячно), журнал: `journalctl -u syscleaner`.
- **Задачи в YAML** — добавляй свои без правки кода.
- Один запрос пароля на весь пакет root-задач (pkexec).

## Установка

```bash
# .deb (рекомендуется)
sudo apt install ./syscleaner_0.2.0_all.deb

# AppImage
chmod +x SysCleaner-0.2.0-x86_64.AppImage && ./SysCleaner-0.2.0-x86_64.AppImage

# из исходников
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml policykit-1
python3 -m syscleaner
```

> AppImage использует системные `python3-gi`/GTK3 (в Mint/Ubuntu/Debian с рабочим столом они уже есть).
> Расписание из AppImage привязывается к пути файла — не перемещай его после включения.

## CLI

```bash
syscleaner --list                                   # список задач
syscleaner --headless --dry-run --tasks tmp,thumbs  # предпросмотр без GUI
sudo syscleaner --headless --tasks apt_clean,tmp --user $USER
```

## Свои задачи (YAML)

Встроенные задачи лежат в `syscleaner/data/tasks.yaml`. Свои — в `~/.config/syscleaner/tasks.d/*.yaml`:

```yaml
groups:
  - {id: mine, title: "⭐ Мои"}
tasks:
  - id: my_cache
    group: mine                      # id группы
    title: "Кэш моего приложения"
    desc: Что делает и чем рискуем
    cmd: rm -rf ~/.cache/myapp/*     # для root: true — без sudo
    risk: safe                       # safe | caution | danger
    estimate: sz ~/.cache/myapp      # число байт; sz — суммарный размер путей
    preview: ls -la ~/.cache/myapp | head
    schedule: true                   # можно в расписание (danger нельзя никогда)
  - id: brave                        # скрыть встроенную задачу
    disabled: true
```
Поля: `root`, `default`, `requires` (программа, без которой задача серая). Ошибки в YAML показываются предупреждением в логе.

## Сборка

```bash
make check      # проверка кода и YAML
make deb        # dist/syscleaner_<ver>_all.deb
make appimage   # dist/SysCleaner-<ver>-x86_64.AppImage (нужен интернет для appimagetool)
```
Релиз на GitHub собирается автоматически по тегу: `git tag v0.2.0 && git push origin v0.2.0`.

## Безопасность

Намеренно **нет** в программе: `rm -rf /tmp/*`, `rm -rf ~/.cache/*`, `docker system prune -a --volumes`,
ручного удаления ядер, `truncate` логов. Опасные задачи не попадают в расписание.

Лицензия: MIT.
