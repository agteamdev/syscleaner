"""Update check against the GitHub Releases API (no GTK here, testable anywhere)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import links


def parse_version(text: str) -> tuple:
    """'v0.4.0' -> (0, 4, 0, 0): up to four numeric parts, padded so tuples compare correctly."""
    nums = [int(n) for n in re.findall(r"\d+", str(text).split("-")[0].split("+")[0])][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check(current: str, url: str = links.API_RELEASES, timeout: float = 6.0) -> dict:
    """Ask GitHub for the newest published (non-draft, non-prerelease) release.

    Returns {"ok": bool, "latest": str|None, "url": str|None, "newer": bool, "error": code}
    where code is "", "offline", "rate_limit", "bad_response" or "http_<status>".
    Never raises: a missing network is a normal situation for this tool.
    """
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"SysCleaner/{current}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            releases = json.load(resp)
    except urllib.error.HTTPError as e:
        why = "rate_limit" if e.code in (403, 429) else f"http_{e.code}"
        return {"ok": False, "latest": None, "url": None, "newer": False, "error": why}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"ok": False, "latest": None, "url": None, "newer": False, "error": "offline"}
    except ValueError:
        return {"ok": False, "latest": None, "url": None, "newer": False, "error": "bad_response"}

    best = None
    for rel in releases if isinstance(releases, list) else []:
        if not isinstance(rel, dict) or rel.get("draft") or rel.get("prerelease") or not rel.get("tag_name"):
            continue
        if best is None or parse_version(rel["tag_name"]) > parse_version(best["tag_name"]):
            best = rel
    if best is None:
        return {"ok": True, "latest": None, "url": links.RELEASES_URL, "newer": False, "error": ""}
    tag = str(best["tag_name"])
    return {"ok": True, "latest": tag.lstrip("vV"), "url": str(best.get("html_url") or links.RELEASES_URL),
            "newer": is_newer(tag, current), "error": ""}
