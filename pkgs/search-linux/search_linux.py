#!/usr/bin/env python3
"""Search (Linux port): a small, quiet browser in the spirit of Search for the Mac (searchbrowser.app).

An unofficial port by its user. The original is (c) 2026 Office Commun, MIT licence; this port keeps
that licence. GTK 4 + libadwaita + WebKitGTK 6 (the Linux build of the engine the Mac app uses).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, WebKit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from searchcore import Store, address_to_url, unique_path  # noqa: E402

APP_ID = "local.searchlinux.Search"
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "search-linux"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "search-linux"
DOWNLOADS = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or Path.home() / "Downloads")

CSS = """
.sidebar { background: @sidebar_bg_color; }
.address { min-height: 30px; border-radius: 8px; padding: 0 8px; font-size: 13px;
           background: alpha(currentColor, 0.06); box-shadow: none; border: none; }
.address:focus-within { background: @view_bg_color; box-shadow: 0 0 0 1px alpha(currentColor, 0.15); }
.tabs, .tabs > row { background: transparent; }
.tabs > row { border-radius: 8px; padding: 0; margin: 1px 0; min-height: 32px; }
.tabs > row:selected { background: alpha(currentColor, 0.09); color: inherit; }
.tabs > row:hover:not(:selected) { background: alpha(currentColor, 0.04); }
.tabtitle { font-size: 13px; }
.tabs > row:not(:selected) .tabtitle { color: alpha(currentColor, 0.72); }
.badge { min-width: 16px; min-height: 16px; border-radius: 4px; font-size: 9px; font-weight: 600;
         background: alpha(currentColor, 0.07); color: alpha(currentColor, 0.55); }
.badge.private { background: alpha(#8a5cf6, 0.18); color: #6d3fd8; }
.closebtn { min-width: 20px; min-height: 20px; padding: 0; border-radius: 5px; opacity: 0; }
.tabs > row:hover .closebtn, .tabs > row:selected .closebtn { opacity: 0.55; }
.newtab { font-size: 13px; color: alpha(currentColor, 0.45); border-radius: 8px; min-height: 30px; padding: 0 8px; }
.pin { min-width: 36px; min-height: 36px; border-radius: 8px; padding: 0; font-size: 12px;
       background: alpha(currentColor, 0.06); color: alpha(currentColor, 0.5); }
.quiet { color: alpha(currentColor, 0.5); min-width: 28px; min-height: 28px; padding: 0; border-radius: 7px; }
.loadbar { min-height: 2px; }
.loadbar trough { min-height: 2px; background: transparent; border: none; }
.loadbar progress { min-height: 2px; border-radius: 0; }
.panel-row { padding: 6px 10px; }
.dim { color: alpha(currentColor, 0.5); font-size: 12px; }
"""


class Tab:
    """One tab. Its WebView is made the first time it is shown, so restored tabs cost nothing until clicked."""

    def __init__(self, url: str | None = None, title: str = "", private: bool = False) -> None:
        self.url, self.title, self.private = url, title, private
        self.view: WebKit.WebView | None = None
        self.row: Gtk.ListBoxRow | None = None
        self.badge: Gtk.Stack | None = None
        self.label: Gtk.Label | None = None


class Browser(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="Search")
        self.set_default_size(1280, 820)
        self.store = Store(DATA)
        self.tabs: list[Tab] = []
        self.closed: list[tuple[str, bool]] = []  # for Ctrl+Shift+T
        self.downloads: list[dict] = []
        self.current: Tab | None = None

        DATA.mkdir(parents=True, exist_ok=True)
        self.session = WebKit.NetworkSession.new(str(DATA / "webkit"), str(CACHE / "webkit"))
        self.session.get_website_data_manager().set_favicons_enabled(True)
        self.session.connect("download-started", self._on_download)
        self.private_session: WebKit.NetworkSession | None = None

        # ---- page side: the views in a stack, a 2 px load bar and the find bar over them
        self.stack = Gtk.Stack(hexpand=True, vexpand=True, transition_type=Gtk.StackTransitionType.NONE)
        self.loadbar = Gtk.ProgressBar(css_classes=["loadbar"], valign=Gtk.Align.START, visible=False)
        self.find_entry = Gtk.SearchEntry(placeholder_text="Find on page", width_chars=28)
        self.find_entry.connect("search-changed", lambda e: self._find(e.get_text()))
        self.find_entry.connect("activate", lambda *_: self._find_step(1))
        self.find_entry.connect("stop-search", lambda *_: self._close_find())
        self.findbar = Gtk.SearchBar(child=self.find_entry, show_close_button=True, valign=Gtk.Align.START)
        self.findbar.connect_entry(self.find_entry)
        page = Gtk.Overlay(child=self.stack)
        page.add_overlay(self.loadbar)
        page.add_overlay(self.findbar)
        self.toasts = Adw.ToastOverlay(child=page)

        # ---- the column: address, pins, tabs, + New tab, and a quiet row of buttons at the bottom
        self.address = Gtk.Entry(css_classes=["address"], placeholder_text="Search or enter address", hexpand=True)
        self.address.connect("activate", self._on_address)
        self.address.connect("changed", self._on_address_changed)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_address_key)
        self.address.add_controller(keys)
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda *_: GLib.idle_add(self.address.select_region, 0, -1))
        focus.connect("leave", lambda *_: self._show_url())
        self.address.add_controller(focus)
        self.suggest_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.suggest_list.connect("row-activated", lambda _l, r: self._go(r.url))
        self.suggest = Gtk.Popover(child=self.suggest_list, autohide=False, has_arrow=False,
                                   position=Gtk.PositionType.BOTTOM, halign=Gtk.Align.START)
        self.suggest.set_parent(self.address)

        nav = Gtk.Box(spacing=2, halign=Gtk.Align.END)
        for icon, tip, fn in (("go-previous-symbolic", "Back (Alt+←)", lambda *_: self._view() and self._view().go_back()),
                              ("go-next-symbolic", "Forward (Alt+→)", lambda *_: self._view() and self._view().go_forward()),
                              ("view-refresh-symbolic", "Reload (Ctrl+R)", lambda *_: self._reload(False))):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat", "quiet"])
            b.connect("clicked", fn)
            nav.append(b)
        top = Gtk.WindowHandle(child=nav)  # drag the window from the empty top of the column

        self.pins = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6, min_children_per_line=6,
                                column_spacing=6, row_spacing=6, halign=Gtk.Align.START)
        self.tablist = Gtk.ListBox(css_classes=["tabs"], selection_mode=Gtk.SelectionMode.SINGLE)
        self.tablist.connect("row-selected", self._on_row_selected)
        newtab = Gtk.Button(css_classes=["flat", "newtab"], halign=Gtk.Align.FILL)
        nb = Gtk.Box(spacing=8)
        nb.append(Gtk.Image(icon_name="list-add-symbolic", pixel_size=12))
        nb.append(Gtk.Label(label="New tab", xalign=0))
        newtab.set_child(nb)
        newtab.connect("clicked", lambda *_: self.new_tab(focus=True))
        tabs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        tabs_box.append(self.tablist)
        tabs_box.append(newtab)
        scroller = Gtk.ScrolledWindow(child=tabs_box, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)

        bottom = Gtk.Box(spacing=2)
        self.history_btn = self._panel_button("document-open-recent-symbolic", "History (Ctrl+Y)", self._fill_history)
        self.downloads_btn = self._panel_button("folder-download-symbolic", "Downloads (Ctrl+Shift+J)", self._fill_downloads)
        self.star = Gtk.Button(icon_name="search-linux-star-symbolic", tooltip_text="Bookmark this page (Ctrl+Shift+B)",
                               css_classes=["flat", "quiet"])
        self.star.connect("clicked", lambda *_: self.toggle_bookmark())
        about = Gtk.Button(icon_name="search-linux-info-symbolic", tooltip_text="About", css_classes=["flat", "quiet"])
        about.connect("clicked", lambda *_: self._about())
        for w in (self.history_btn, self.downloads_btn, self.star):
            bottom.append(w)
        bottom.append(Gtk.Box(hexpand=True))
        bottom.append(about)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["sidebar"], hexpand=False,
                      margin_top=8, margin_bottom=8, margin_start=10, margin_end=10, width_request=236)
        for w in (top, self.address, self.pins, scroller, bottom):
            col.append(w)
        side_bg = Gtk.Box(css_classes=["sidebar"], hexpand=False)  # the address field must not widen the column
        side_bg.append(col)
        self.sidebar = Gtk.Revealer(child=side_bg, reveal_child=True,
                                    transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT, transition_duration=160)
        root = Gtk.Box()
        root.append(self.sidebar)
        root.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        root.append(self.toasts)
        self.set_content(root)

        self._shortcuts()
        self._fill_pins()
        self.connect("close-request", self._on_close)

        sess = self.store.session()
        for u in sess.get("tabs", []):
            self.new_tab(u, lazy=True)
        if self.tabs:
            self.select(self.tabs[min(sess.get("active", 0), len(self.tabs) - 1)])
        else:
            self.new_tab(focus=True)

    # ---- tabs ----------------------------------------------------------------------------------------
    def _make_view(self, tab: Tab, related: WebKit.WebView | None = None) -> WebKit.WebView:
        if related is not None:
            view = WebKit.WebView(related_view=related)
        else:
            if tab.private and self.private_session is None:
                self.private_session = WebKit.NetworkSession.new_ephemeral()
                self.private_session.connect("download-started", self._on_download)
            view = WebKit.WebView(network_session=self.private_session if tab.private else self.session)
        s = view.get_settings()
        s.set_enable_developer_extras(True)  # Inspect Element in the right-click menu
        s.set_enable_smooth_scrolling(True)
        view.connect("notify::title", lambda v, _p: self._on_title(tab))
        view.connect("notify::uri", lambda v, _p: self._on_uri(tab))
        view.connect("notify::favicon", lambda v, _p: self._on_favicon(tab))
        view.connect("notify::estimated-load-progress", lambda v, _p: self._on_progress(tab))
        view.connect("load-changed", lambda v, ev: self._on_load(tab, ev))
        view.connect("create", lambda v, action: self._on_create(tab))
        view.connect("decide-policy", self._on_policy)
        tab.view = view
        self.stack.add_child(view)
        return view

    def new_tab(self, url: str | None = None, lazy: bool = False, focus: bool = False, private: bool = False,
                background: bool = False, after: Tab | None = None, related: WebKit.WebView | None = None) -> Tab:
        tab = Tab(url, title=url or "New tab", private=private)
        tab.row = self._tab_row(tab)
        pos = self.tabs.index(after) + 1 if after in self.tabs else len(self.tabs)
        self.tabs.insert(pos, tab)
        self.tablist.insert(tab.row, pos)
        if not lazy:
            self._make_view(tab, related)
            if url:
                tab.view.load_uri(url)
        if not background and not lazy:
            self.select(tab)
        if focus:
            self.focus_address()
        return tab

    def _tab_row(self, tab: Tab) -> Gtk.ListBoxRow:
        tab.badge = Gtk.Stack(css_classes=["badge"] + (["private"] if tab.private else []), valign=Gtk.Align.CENTER)
        tab.badge.add_named(Gtk.Label(label=self._letter(tab)), "letter")
        tab.label = Gtk.Label(label=tab.title, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END,
                              css_classes=["tabtitle"])
        close = Gtk.Button(icon_name="window-close-symbolic", css_classes=["flat", "closebtn"], valign=Gtk.Align.CENTER,
                           tooltip_text="Close tab (Ctrl+W)")
        close.connect("clicked", lambda *_: self.close_tab(tab))
        box = Gtk.Box(spacing=8, margin_start=8, margin_end=4)
        for w in (tab.badge, tab.label, close):
            box.append(w)
        middle = Gtk.GestureClick(button=2)
        middle.connect("released", lambda *_: self.close_tab(tab))
        box.add_controller(middle)
        row = Gtk.ListBoxRow(child=box)
        row.tab = tab
        return row

    @staticmethod
    def _letter(tab: Tab) -> str:
        if tab.private:
            return "P"
        host = GLib.Uri.peek_scheme(tab.url or "") and (GLib.Uri.parse(tab.url, GLib.UriFlags.NONE).get_host() or "")
        name = (host or tab.title or "").removeprefix("www.")
        return (name[:1] or "·").upper()

    def select(self, tab: Tab) -> None:
        if tab.row is not self.tablist.get_selected_row():
            self.tablist.select_row(tab.row)
            return  # row-selected brings us back here through _on_row_selected
        self._activate(tab)

    def _on_row_selected(self, _list, row) -> None:
        if row is not None:
            self._activate(row.tab)

    def _activate(self, tab: Tab) -> None:
        self.current = tab
        if tab.view is None:
            self._make_view(tab)
            if tab.url:
                tab.view.load_uri(tab.url)
        self.stack.set_visible_child(tab.view)
        self._show_url()
        self._on_progress(tab)
        self._sync_star()
        self.set_title(f"{tab.title} — Search" if tab.title else "Search")
        if self.findbar.get_search_mode():
            self._find(self.find_entry.get_text())
        if not tab.url:
            self.focus_address()
        else:
            tab.view.grab_focus()

    def close_tab(self, tab: Tab | None = None) -> None:
        tab = tab or self.current
        if tab is None:
            return
        i = self.tabs.index(tab)
        if tab.url and not tab.private:
            self.closed.append((tab.url, tab.private))
        self.tabs.remove(tab)
        self.tablist.remove(tab.row)
        if tab.view is not None:
            self.stack.remove(tab.view)
            tab.view.try_close()
        if not self.tabs:
            self.new_tab(focus=True)
        elif tab is self.current:
            self.select(self.tabs[min(i, len(self.tabs) - 1)])

    def reopen(self) -> None:
        if self.closed:
            url, private = self.closed.pop()
            self.new_tab(url, private=private)

    def cycle(self, step: int) -> None:
        if self.current in self.tabs and len(self.tabs) > 1:
            self.select(self.tabs[(self.tabs.index(self.current) + step) % len(self.tabs)])

    def jump(self, n: int) -> None:
        if self.tabs:
            self.select(self.tabs[-1] if n == 9 else self.tabs[min(n - 1, len(self.tabs) - 1)])

    def _view(self) -> WebKit.WebView | None:
        return self.current.view if self.current else None

    # ---- page events ---------------------------------------------------------------------------------
    def _on_title(self, tab: Tab) -> None:
        t = tab.view.get_title() or tab.url or "New tab"
        tab.title = t
        tab.label.set_label(t)
        if tab is self.current:
            self.set_title(f"{t} — Search")

    def _on_uri(self, tab: Tab) -> None:
        tab.url = tab.view.get_uri()
        letter = tab.badge.get_child_by_name("letter")
        letter.set_label(self._letter(tab))
        if tab is self.current:
            self._show_url()
            self._sync_star()

    def _on_favicon(self, tab: Tab) -> None:
        tex = tab.view.get_favicon()
        old = tab.badge.get_child_by_name("icon")
        if old:
            tab.badge.remove(old)
        if tex is not None and not tab.private:
            tab.badge.add_named(Gtk.Image(paintable=tex, pixel_size=16), "icon")
            tab.badge.set_visible_child_name("icon")
        else:
            tab.badge.set_visible_child_name("letter")

    def _on_progress(self, tab: Tab) -> None:
        if tab is not self.current or tab.view is None:
            return
        p = tab.view.get_estimated_load_progress()
        loading = tab.view.is_loading() and p < 1.0
        self.loadbar.set_visible(loading)
        self.loadbar.set_fraction(p)

    def _on_load(self, tab: Tab, event) -> None:
        if event == WebKit.LoadEvent.FINISHED:
            self._on_progress(tab)
            if not tab.private:
                self.store.visit(tab.view.get_uri() or "", tab.view.get_title() or "")

    def _on_create(self, parent: Tab):
        """target=_blank and window.open become tabs: there is one window and tabs are the only kind of new."""
        tab = self.new_tab(after=parent, related=parent.view, private=parent.private)
        return tab.view

    def _on_policy(self, view, decision, kind) -> bool:
        if kind == WebKit.PolicyDecisionType.RESPONSE:
            if not decision.is_mime_type_supported():  # a file WebKit can't show (zip, pdf, ...): download it
                decision.download()
                return True
            return False
        if kind != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            return False
        action = decision.get_navigation_action()
        if action.get_navigation_type() != WebKit.NavigationType.LINK_CLICKED:
            return False
        if action.get_mouse_button() == 2 or action.get_modifiers() & Gdk.ModifierType.CONTROL_MASK:
            parent = next(t for t in self.tabs if t.view is view)
            self.new_tab(action.get_request().get_uri(), background=True, after=parent, private=parent.private)
            decision.ignore()
            return True
        return False

    # ---- address field -------------------------------------------------------------------------------
    def focus_address(self) -> None:
        self.sidebar.set_reveal_child(True)
        self.address.grab_focus()

    def _show_url(self) -> None:
        if self.address.has_focus():
            return
        self.suggest.popdown()
        url = self.current.url if self.current else ""
        self.address.set_text("" if not url or url == "about:blank" else url)

    def _go(self, url: str | None) -> None:
        self.suggest.popdown()
        if not url:
            return
        if self.current is None:
            self.new_tab(url)
            return
        if self.current.view is None:
            self._make_view(self.current)
        self.current.url = url
        self.current.view.load_uri(url)
        self.current.view.grab_focus()

    def _on_address(self, entry: Gtk.Entry) -> None:
        self._go(address_to_url(entry.get_text(), self.store.search_url))

    def _on_address_changed(self, entry: Gtk.Entry) -> None:
        if not entry.has_focus():
            return
        while (row := self.suggest_list.get_row_at_index(0)) is not None:
            self.suggest_list.remove(row)
        hits = self.store.suggest(entry.get_text(), limit=6)
        for e in hits:
            self.suggest_list.append(self._entry_row(e["title"] or e["url"], e["url"]))
        if hits:
            self.suggest.popup()
        else:
            self.suggest.popdown()

    def _on_address_key(self, _c, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Down and self.suggest.is_visible():
            row = self.suggest_list.get_row_at_index(0)
            if row:
                row.grab_focus()
            return True
        if keyval == Gdk.KEY_Escape:
            self.suggest.popdown()
            self._view() and self._view().grab_focus()
            return True
        return False

    # ---- panels: history, downloads ------------------------------------------------------------------
    def _panel_button(self, icon: str, tip: str, fill) -> Gtk.MenuButton:
        lst = Gtk.ListBox(css_classes=["navigation-sidebar"])
        search = Gtk.SearchEntry(placeholder_text="Search")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=380)
        box.append(search)
        box.append(Gtk.ScrolledWindow(child=lst, min_content_height=320, max_content_height=480,
                                      propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        pop = Gtk.Popover(child=box)
        pop.connect("show", lambda *_: (search.set_text(""), fill(lst, ""), search.grab_focus()))
        search.connect("search-changed", lambda e: fill(lst, e.get_text()))
        lst.connect("row-activated", lambda _l, r: (pop.popdown(), r.on_open()))
        return Gtk.MenuButton(icon_name=icon, tooltip_text=tip, popover=pop, css_classes=["flat", "quiet"],
                              direction=Gtk.ArrowType.UP)

    def _entry_row(self, title: str, sub: str, on_open=None) -> Gtk.ListBoxRow:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["panel-row"])
        box.append(Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END))
        box.append(Gtk.Label(label=sub, xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, css_classes=["dim"]))
        row = Gtk.ListBoxRow(child=box)
        row.url = sub
        row.on_open = on_open or (lambda: self._go(sub))
        return row

    @staticmethod
    def _clear(lst: Gtk.ListBox) -> None:
        while (row := lst.get_row_at_index(0)) is not None:
            lst.remove(row)

    def _fill_history(self, lst: Gtk.ListBox, text: str) -> None:
        self._clear(lst)
        t = text.lower()
        items = [e for e in self.store.history() if t in e["url"].lower() or t in e["title"].lower()][:200]
        for e in items:
            lst.append(self._entry_row(e["title"] or e["url"], e["url"]))
        if not items:
            lst.append(Gtk.ListBoxRow(child=Gtk.Label(label="No history yet", css_classes=["dim"], margin_top=12,
                                                       margin_bottom=12), activatable=False))

    def _fill_downloads(self, lst: Gtk.ListBox, text: str) -> None:
        self._clear(lst)
        items = [d for d in reversed(self.downloads) if text.lower() in d["name"].lower()]
        for d in items:
            state = {"done": "Done — click to open", "failed": "Failed"}.get(d["state"], f"{int(d['progress'] * 100)} %")
            lst.append(self._entry_row(d["name"], f"{state} · {d['path']}",
                                       on_open=lambda p=d["path"]: Gio.AppInfo.launch_default_for_uri(
                                           GLib.filename_to_uri(p), None)))
        if not items:
            lst.append(Gtk.ListBoxRow(child=Gtk.Label(label="No downloads yet", css_classes=["dim"], margin_top=12,
                                                       margin_bottom=12), activatable=False))

    def _on_download(self, _session, download: WebKit.Download) -> None:
        item = {"name": "download", "path": "", "progress": 0.0, "state": "running"}
        self.downloads.append(item)

        def destination(d, suggested):
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            p = unique_path(DOWNLOADS, suggested)
            item.update(name=p.name, path=str(p))
            d.set_destination(str(p))
            self.toasts.add_toast(Adw.Toast(title=f"Downloading {p.name}", timeout=2))
            return True

        download.connect("decide-destination", destination)
        download.connect("notify::estimated-progress",
                         lambda d, _p: item.update(progress=d.get_estimated_progress()))
        download.connect("finished", lambda d: item["state"] == "running" and (
            item.update(state="done", progress=1.0), self.toasts.add_toast(Adw.Toast(title=f"Downloaded {item['name']}",
                                                                                       timeout=3))))
        download.connect("failed", lambda d, err: item.update(state="failed"))

    # ---- bookmarks (pins) ----------------------------------------------------------------------------
    def toggle_bookmark(self) -> None:
        t = self.current
        if t and t.url and t.url.startswith(("http", "file")):
            added = self.store.toggle_bookmark(t.url, t.title)
            self.toasts.add_toast(Adw.Toast(title="Bookmarked" if added else "Bookmark removed", timeout=2))
            self._fill_pins()
            self._sync_star()

    def _sync_star(self) -> None:
        on = bool(self.current and self.current.url and self.store.is_bookmarked(self.current.url))
        self.star.set_icon_name("search-linux-starred-symbolic" if on else "search-linux-star-symbolic")

    def _fill_pins(self) -> None:
        while (c := self.pins.get_child_at_index(0)) is not None:
            self.pins.remove(c)
        bms = self.store.bookmarks()
        for b in bms:
            host = GLib.Uri.parse(b["url"], GLib.UriFlags.NONE).get_host() or b["title"] or "?"
            btn = Gtk.Button(label=host.removeprefix("www.")[:1].upper(), css_classes=["pin", "flat"],
                             tooltip_text=b["title"] or b["url"], halign=Gtk.Align.START, hexpand=False)
            btn.connect("clicked", lambda _b, u=b["url"]: self._open_pin(u))
            self.pins.append(btn)
        self.pins.set_visible(bool(bms))

    def _open_pin(self, url: str) -> None:
        tab = next((t for t in self.tabs if t.url == url), None)
        if tab:
            self.select(tab)
        else:
            self.new_tab(url)

    # ---- find, reload, misc --------------------------------------------------------------------------
    def _find(self, text: str) -> None:
        v = self._view()
        if v is None:
            return
        fc = v.get_find_controller()
        if text:
            fc.search(text, WebKit.FindOptions.CASE_INSENSITIVE | WebKit.FindOptions.WRAP_AROUND, 1000)
        else:
            fc.search_finish()

    def _find_step(self, step: int) -> None:
        v = self._view()
        if v:
            (v.get_find_controller().search_next if step > 0 else v.get_find_controller().search_previous)()

    def _close_find(self) -> None:
        self.findbar.set_search_mode(False)
        v = self._view()
        if v:
            v.get_find_controller().search_finish()
            v.grab_focus()

    def _reload(self, bypass: bool) -> None:
        v = self._view()
        if v:
            v.reload_bypass_cache() if bypass else v.reload()

    def _zoom(self, factor: float | None) -> None:
        v = self._view()
        if v:
            v.set_zoom_level(1.0 if factor is None else max(0.3, min(3.0, v.get_zoom_level() * factor)))

    def _copy_address(self) -> None:
        if self.current and self.current.url:
            self.get_clipboard().set(self.current.url)
            self.toasts.add_toast(Adw.Toast(title="Address copied", timeout=1))

    def _paste_and_go(self) -> None:
        def done(cb, res):
            text = cb.read_text_finish(res)
            if text:
                self.new_tab(address_to_url(text, self.store.search_url))
        self.get_clipboard().read_text_async(None, done)

    def _escape(self) -> None:
        if self.findbar.get_search_mode():
            self._close_find()
        elif self.suggest.is_visible():
            self.suggest.popdown()
        elif self._view() and self._view().is_loading():
            self._view().stop_loading()

    def _about(self) -> None:
        dlg = Adw.AboutDialog(
            application_name="Search (Linux port)", application_icon=APP_ID, version="0.1",
            developer_name="Unofficial port", license_type=Gtk.License.MIT_X11, website="https://searchbrowser.app",
            comments="A small, quiet browser in the spirit of Search for the Mac, on WebKitGTK.\n"
                     "Not affiliated with Office Commun. Passwords are not stored by this port.",
            copyright="Search © 2026 Office Commun (MIT). Linux port under the same licence.")
        dlg.add_credit_section("Original app", ["Office Commun https://officecommun.com"])
        dlg.present(self)

    def _shortcuts(self) -> None:
        ctl = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL, propagation_phase=Gtk.PropagationPhase.CAPTURE)

        def add(triggers: str, fn) -> None:
            def cb(*_a):
                fn()
                return True
            for t in triggers.split("|"):
                ctl.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string(t),
                                              action=Gtk.CallbackAction.new(cb)))

        v = self._view
        add("<Control>l|F6|<Alt>d", self.focus_address)
        add("<Control>t", lambda: self.new_tab(focus=True))
        add("<Control><Shift>n", lambda: self.new_tab(focus=True, private=True))
        add("<Control>w|<Control>F4", self.close_tab)
        add("<Control><Shift>t", self.reopen)
        add("<Alt>Left|<Control>bracketleft", lambda: v() and v().go_back())
        add("<Alt>Right|<Control>bracketright", lambda: v() and v().go_forward())
        add("<Control>r|F5", lambda: self._reload(False))
        add("<Control><Shift>r|<Shift>F5", lambda: self._reload(True))
        add("<Control>Tab|<Control>Page_Down|<Control><Shift>bracketright", lambda: self.cycle(1))
        add("<Control><Shift>Tab|<Control><Shift>ISO_Left_Tab|<Control>Page_Up|<Control><Shift>bracketleft",
            lambda: self.cycle(-1))
        for n in range(1, 10):
            add(f"<Control>{n}|<Alt>{n}", lambda n=n: self.jump(n))
        add("<Control>s", lambda: self.sidebar.set_reveal_child(not self.sidebar.get_reveal_child()))
        add("<Control><Shift>b|<Control>d", self.toggle_bookmark)
        add("<Control>y|<Control>h", lambda: self.history_btn.popup())
        add("<Control><Shift>j", lambda: self.downloads_btn.popup())
        add("<Control>f", lambda: (self.findbar.set_search_mode(True), self.find_entry.grab_focus()))
        add("<Control>g", lambda: self._find_step(1))
        add("<Control><Shift>g", lambda: self._find_step(-1))
        add("<Control><Shift>c", self._copy_address)
        add("<Control><Shift>v", self._paste_and_go)
        add("<Control>plus|<Control>equal", lambda: self._zoom(1.1))
        add("<Control>minus", lambda: self._zoom(1 / 1.1))
        add("<Control>0", lambda: self._zoom(None))
        add("F11", lambda: self.unfullscreen() if self.is_fullscreen() else self.fullscreen())
        add("Escape", self._escape)
        add("<Control>q", self.close)
        self.add_controller(ctl)

    def _on_close(self, *_a) -> bool:
        normal = [t for t in self.tabs if not t.private]
        active = normal.index(self.current) if self.current in normal else 0
        self.store.save_session([t.url or "" for t in normal], active)
        return False


class App(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win: Browser | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # our own star and info icons: icon themes such as Zafiro lack the Adwaita names
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(
            str(Path(__file__).resolve().parent / "icons"))

    def do_activate(self) -> None:
        if self.win is None:
            self.win = Browser(self)
        self.win.present()

    def do_open(self, files, _n, _hint) -> None:
        self.do_activate()
        for f in files:
            self.win.new_tab(f.get_uri())


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":  # scripted check, see selftest.py
        from selftest import run
        return run(App, Path(sys.argv[2]))
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
