# Search (Linux port)

An unofficial Linux port of [Search](https://searchbrowser.app), the small, quiet Mac browser by
[Office Commun](https://officecommun.com) ([source](https://github.com/driceroland/Search), MIT).
Not affiliated with Office Commun. The icon is their mark, redrawn from `Icon/icon.swift` under the MIT licence
(`LICENSE.upstream` is their licence text, kept as it requires).

GTK 4 + libadwaita + WebKitGTK 6.0, in Python (PyGObject): one window, tabs down the left, one field that goes to an
address or searches (Google, as the Mac app's default; change it with `search_url` in
`~/.local/share/search-linux/settings.json`), history, downloads, bookmarks as pins, private tabs, find, and the Mac
app's shortcuts with Ctrl for ⌘. Passwords are not stored by this port.

    nix build .#search-linux      # or: python3 search_linux.py (needs GTK4, libadwaita, WebKitGTK 6 and PyGObject)
    python -m pytest tests        # the address, history, bookmark and download-name logic
