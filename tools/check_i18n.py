#!/usr/bin/env python3
"""Verify translation catalogs against the code and tasks.yaml.

Usage: python3 tools/check_i18n.py [--list]
  --list  print every UI string that needs translating (handy for a new language).
"""
import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "syscleaner"
PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def source_strings():
    found = set()
    for py in PKG.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    return found


def main():
    src = source_strings()
    if "--list" in sys.argv:
        print("\n".join(sorted(src)))
        return 0
    base = yaml.safe_load((PKG / "data" / "tasks.yaml").read_text(encoding="utf-8"))
    gids = {g["id"] for g in base["groups"]}
    tids = {t["id"] for t in base["tasks"]}
    bad = 0
    for cat_file in sorted((PKG / "data" / "i18n").glob("*.yaml")):
        cat = yaml.safe_load(cat_file.read_text(encoding="utf-8"))
        ui, groups, tasks = cat.get("ui") or {}, cat.get("groups") or {}, cat.get("tasks") or {}
        problems = []
        if not (cat.get("meta") or {}).get("name"):
            problems.append("missing meta.name (the native language name shown in the language picker)")
        problems += [f"missing ui string: {s!r}" for s in sorted(src - set(ui))]
        problems += [f"stale ui string: {s!r}" for s in sorted(set(ui) - src)]
        problems += [f"missing group: {g}" for g in sorted(gids - set(groups))]
        problems += [f"missing task: {t}" for t in sorted(tids - set(tasks))]
        problems += [f"unknown group/task: {k}" for k in sorted((set(groups) - gids) | (set(tasks) - tids))]
        for k, v in ui.items():
            if sorted(PLACEHOLDER.findall(k)) != sorted(PLACEHOLDER.findall(str(v))):
                problems.append(f"placeholder mismatch: {k!r}")
        for tid, tr in tasks.items():
            if not (isinstance(tr, dict) and tr.get("title") and tr.get("desc")):
                problems.append(f"task {tid}: needs title and desc")
        print(f"{cat_file.name}: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
        for p in problems:
            print("  -", p)
        bad += len(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
