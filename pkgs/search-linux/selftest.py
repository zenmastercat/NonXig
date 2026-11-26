"""Scripted check of the real browser: `search-linux --selftest OUTDIR` (use a throwaway XDG_DATA_HOME).

Drives the same methods the keys and clicks call, saves window-only PNGs with GTK's own renderer and writes
results.json. Needs the network (example.com, a search, searchbrowser.app, one small public PDF).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import gi

gi.require_version("Graphene", "1.0")
from gi.repository import GLib, Graphene, Gtk  # noqa: E402

ZIP = "https://github.com/octocat/Hello-World/archive/refs/heads/master.zip"  # small; a PDF would open in WebKit's viewer


def shot(widget: Gtk.Widget, path: Path) -> bool:
    """Save the widget as drawn now; False (try again) while GTK has nothing painted yet."""
    w, h = widget.get_width(), widget.get_height()
    snap = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(widget).snapshot(snap, w, h)
    node = snap.to_node()
    if node is None or not w or not h:
        return False
    widget.get_native().get_renderer().render_texture(node, Graphene.Rect().init(0, 0, w, h)).save_to_png(str(path))
    return True


def pause(seconds: float):
    return (lambda: False), seconds, True


def run(App, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    main = sys.modules["__main__"]
    main.DOWNLOADS = out / "downloads"  # keep test files out of ~/Downloads
    app = App()
    res: dict = {"steps": []}

    def loaded(win, host: str):
        v = win._view()
        return lambda: v is not None and not v.is_loading() and host in (v.get_uri() or "")

    def script(win):
        win.store.search_url = "https://duckduckgo.com/?q=%s"  # Google answers scripted runs with its captcha page
        win._go("https://example.com")
        yield loaded(win, "example.com"), 20
        res["steps"].append("example.com loaded")
        win.new_tab(focus=True)
        win.address.set_text("webkitgtk browser")
        win._on_address(win.address)
        yield loaded(win, "duckduckgo"), 25
        res["steps"].append("search from the address field: " + (win._view().get_uri() or ""))
        win.new_tab("https://searchbrowser.app")
        yield loaded(win, "searchbrowser.app"), 25
        win.toggle_bookmark()
        win.select(win.tabs[0])
        win.toggle_bookmark()
        res["steps"].append("bookmarked 2 pages")
        n = len(win.tabs)
        win.new_tab(ZIP)
        yield (lambda: any(d["state"] != "running" for d in win.downloads)), 40
        res["downloads"] = win.downloads
        win.close_tab()  # the download's empty tab
        win.select(win.tabs[1])
        win.close_tab()
        res["after_close"] = len(win.tabs)
        win.reopen()
        yield loaded(win, "duckduckgo"), 25
        res["after_reopen"] = len(win.tabs)
        res["reopen_ok"] = len(win.tabs) == n and "duckduckgo" in (win._view().get_uri() or "")
        by = lambda host: next(t for t in win.tabs if host in (t.url or ""))  # noqa: E731
        win.select(by("searchbrowser.app"))
        yield loaded(win, "searchbrowser.app"), 10
        yield pause(2)  # favicons and paint settle
        win.present()
        yield (lambda: shot(win, out / "01-search-linux-searchbrowser.png")), 5
        win.select(by("duckduckgo"))
        yield pause(2)
        win.present()
        yield (lambda: shot(win, out / "02-search-linux-results.png")), 5
        win.history_btn.popup()
        yield pause(1)
        yield (lambda: shot(win.history_btn.get_popover(), out / "03-history-panel.png")), 5
        win.history_btn.popdown()
        win.downloads_btn.popup()
        yield pause(1)
        yield (lambda: shot(win.downloads_btn.get_popover(), out / "04-downloads-panel.png")), 5
        win.downloads_btn.popdown()
        res["tabs"] = [t.url for t in win.tabs]
        res["history"] = [e["url"] for e in win.store.history()]
        res["bookmarks"] = [b["url"] for b in win.store.bookmarks()]
        res["files"] = {p.name: p.stat().st_size for p in (out / "downloads").glob("*")} \
            if (out / "downloads").exists() else {}

    def start(application):
        win = application.win
        steps = script(win)
        state = {"cond": None, "left": 0.0, "pause": False}

        def tick():
            cond = state["cond"]
            if cond is not None and not cond() and state["left"] > 0:
                state["left"] -= 0.25
                return True
            if cond is not None and state["left"] <= 0 and not state["pause"] and not cond():
                res["steps"].append(f"wait timed out after: {res['steps'][-1] if res['steps'] else 'start'}")
            try:
                nxt = next(steps)
                state["cond"], state["left"], state["pause"] = (nxt + (False,))[:3]
                return True
            except StopIteration:
                (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
                application.quit()
                return False
            except Exception as e:  # a failed step ends the run with its reason
                import traceback
                res["error"] = traceback.format_exc()
                (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
                application.quit()
                return False

        GLib.timeout_add(250, tick)

    app.connect("activate", lambda a: GLib.idle_add(start, a))
    return app.run([sys.argv[0]])
