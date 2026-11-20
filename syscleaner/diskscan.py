"""Folder scanning with progress (no GTK here, so it can be tested anywhere).

The scan runs one `du` per direct child of the folder and streams markers:
  @@N <count>                      number of children (progress denominator)
  @@CUR <path>                     child that is being measured now
  @@ITEM<TAB>d|f<TAB>bytes<TAB>path  a finished child
  @@END                            done
"""
from __future__ import annotations

import subprocess

SCAN_SCRIPT = r'''P="$1"
mapfile -d '' items < <(find "$P" -mindepth 1 -maxdepth 1 -print0 2>/dev/null)
echo "@@N ${#items[@]}"
for it in "${items[@]}"; do
  echo "@@CUR $it"
  sz=$(du -xsB1 -- "$it" 2>/dev/null | cut -f1)
  if [ -d "$it" ] && [ ! -L "$it" ]; then t=d; else t=f; fi
  printf '@@ITEM\t%s\t%s\t%s\n' "$t" "${sz:-0}" "$it"
done
echo "@@END"
'''


def start(path: str, as_root: bool = False) -> subprocess.Popen:
    argv = ["bash", "-c", SCAN_SCRIPT, "bash", path]
    if as_root:
        argv.insert(0, "pkexec")
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, text=True, errors="replace")


def parse_line(line: str):
    """Return ('n', int) | ('cur', path) | ('item', is_dir, size, path) | ('end',) | None."""
    line = line.rstrip("\n")
    try:
        if line.startswith("@@N "):
            return ("n", int(line[4:]))
        if line.startswith("@@CUR "):
            return ("cur", line[6:])
        if line.startswith("@@ITEM\t"):
            _tag, kind, size, path = line.split("\t", 3)
            return ("item", kind == "d", int(size), path)
        if line == "@@END":
            return ("end",)
    except ValueError:
        pass
    return None
