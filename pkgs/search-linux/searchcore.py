"""Search (Linux port): the parts with no GUI. Address-or-search, history, bookmarks, session, download names.

Data lives in small JSON files, as in the Mac app (there: ~/Library/Application Support/Search/;
here: $XDG_DATA_HOME/search-linux/). Nothing is sent anywhere.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

DEFAULT_SEARCH = "https://www.google.com/search?q=%s"  # the Mac app's default engine (Engine.standard = .google)

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_HOST = re.compile(
    r"^(localhost|\d{1,3}(\.\d{1,3}){3}|[\w-]+(\.[\w-]+)*\.[a-zA-Z]{2,}|\[[0-9a-fA-F:]+\])(:\d{1,5})?([/?#].*)?$"
)


def address_to_url(text: str, search_url: str = DEFAULT_SEARCH) -> str | None:
    """What the one field does: an address goes there, anything else is searched."""
    t = text.strip()
    if not t:
        return None
    if " " not in t:
        if _SCHEME.match(t) and not re.match(r"^[\w.-]+:\d", t):  # "localhost:3000" is a host, not a scheme
            return t
        m = _HOST.match(t)
        if m:
            local = m.group(1) == "localhost" or re.match(r"^\d", m.group(1))
            return ("http://" if local else "https://") + t
    return search_url.replace("%s", quote_plus(t))


def unique_path(folder: Path, name: str) -> Path:
    """A free file name in `folder` for a download, never outside it."""
    base = Path(name).name or "download"
    p = folder / base
    stem, suffix = p.stem, p.suffix
    n = 1
    while p.exists():
        p = folder / f"{stem} ({n}){suffix}"
        n += 1
    return p


def _read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(path)  # atomic: a crash never leaves half a file


class Store:
    def __init__(self, folder: Path, max_history: int = 5000) -> None:
        self.dir = Path(folder)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_history = max_history
        self._history: list[dict] = _read(self.dir / "history.json", [])
        self._bookmarks: list[dict] = _read(self.dir / "bookmarks.json", [])
        settings = _read(self.dir / "settings.json", {})
        self.search_url = settings.get("search_url") or DEFAULT_SEARCH

    # history ------------------------------------------------------------------------------------------
    def visit(self, url: str, title: str) -> None:
        if not url.startswith(("http://", "https://", "file://")):
            return
        old = next((e for e in self._history if e["url"] == url), None)
        if old:
            self._history.remove(old)
        entry = {"url": url, "title": title or (old or {}).get("title", ""), "time": time.time(),
                 "visits": (old or {}).get("visits", 0) + 1}
        self._history.insert(0, entry)
        del self._history[self.max_history:]
        # shortcut: rewrites the whole file per visit; fine for a few thousand entries.
        _write(self.dir / "history.json", self._history)

    def history(self) -> list[dict]:
        return list(self._history)

    def suggest(self, text: str, limit: int = 8) -> list[dict]:
        t = text.strip().lower()
        if not t:
            return []
        hits = [e for e in self._history if t in e["url"].lower() or t in e["title"].lower()]
        return sorted(hits, key=lambda e: -e["visits"])[:limit]

    def clear_history(self) -> None:
        self._history = []
        _write(self.dir / "history.json", self._history)

    # bookmarks ----------------------------------------------------------------------------------------
    def bookmarks(self) -> list[dict]:
        return list(self._bookmarks)

    def is_bookmarked(self, url: str) -> bool:
        return any(b["url"] == url for b in self._bookmarks)

    def toggle_bookmark(self, url: str, title: str) -> bool:
        if self.is_bookmarked(url):
            self._bookmarks = [b for b in self._bookmarks if b["url"] != url]
            added = False
        else:
            self._bookmarks.append({"url": url, "title": title})
            added = True
        _write(self.dir / "bookmarks.json", self._bookmarks)
        return added

    # session ------------------------------------------------------------------------------------------
    def save_session(self, urls: list[str], active: int) -> None:
        keep = [(i, u) for i, u in enumerate(urls) if u and u != "about:blank"]
        idx = next((n for n, (i, _) in enumerate(keep) if i == active), 0)
        _write(self.dir / "session.json", {"tabs": [u for _, u in keep], "active": idx})

    def session(self) -> dict:
        return _read(self.dir / "session.json", {"tabs": [], "active": 0})
