import json

import pytest

from searchcore import Store, address_to_url, unique_path

GOOGLE = "https://www.google.com/search?q=%s"


@pytest.mark.parametrize("text,url", [
    ("example.com", "https://example.com"),
    ("https://example.com/a?b=1", "https://example.com/a?b=1"),
    ("http://localhost:8080", "http://localhost:8080"),
    ("localhost:3000/x", "http://localhost:3000/x"),
    ("192.168.1.135:8765", "http://192.168.1.135:8765"),
    ("about:blank", "about:blank"),
    ("file:///tmp/a.html", "file:///tmp/a.html"),
    ("  sub.domain.co.th/path  ", "https://sub.domain.co.th/path"),
    ("hello world", "https://www.google.com/search?q=hello+world"),
    ("nixos", "https://www.google.com/search?q=nixos"),
    ("what is 2+2?", "https://www.google.com/search?q=what+is+2%2B2%3F"),
    ("หลุมบ่อ", "https://www.google.com/search?q=%E0%B8%AB%E0%B8%A5%E0%B8%B8%E0%B8%A1%E0%B8%9A%E0%B9%88%E0%B8%AD"),
    ("file.txt is here", "https://www.google.com/search?q=file.txt+is+here"),
])
def test_address_to_url(text, url):
    assert address_to_url(text, GOOGLE) == url


def test_empty_address_is_none():
    assert address_to_url("   ", GOOGLE) is None


def test_history_records_and_ranks(tmp_path):
    s = Store(tmp_path)
    s.visit("https://a.com/", "A")
    s.visit("https://b.com/", "B")
    s.visit("https://a.com/", "A again")
    h = s.history()
    assert [e["url"] for e in h] == ["https://a.com/", "https://b.com/"]  # newest first
    assert h[0]["title"] == "A again" and h[0]["visits"] == 2
    assert [e["url"] for e in s.suggest("a.c")] == ["https://a.com/"]
    s2 = Store(tmp_path)  # persisted
    assert len(s2.history()) == 2


def test_history_ignores_blank_and_caps(tmp_path):
    s = Store(tmp_path, max_history=3)
    s.visit("about:blank", "")
    for i in range(5):
        s.visit(f"https://x{i}.com/", "")
    assert [e["url"] for e in s.history()] == ["https://x4.com/", "https://x3.com/", "https://x2.com/"]


def test_bookmarks_toggle_and_session(tmp_path):
    s = Store(tmp_path)
    assert s.toggle_bookmark("https://a.com/", "A") is True
    assert s.is_bookmarked("https://a.com/")
    assert s.toggle_bookmark("https://a.com/", "A") is False
    s.save_session(["https://a.com/", "about:blank", "https://b.com/"], 2)
    assert Store(tmp_path).session() == {"tabs": ["https://a.com/", "https://b.com/"], "active": 1}


def test_corrupt_file_does_not_crash(tmp_path):
    (tmp_path / "history.json").write_text("{not json")
    assert Store(tmp_path).history() == []


def test_settings_default_engine(tmp_path):
    assert Store(tmp_path).search_url == GOOGLE
    (tmp_path / "settings.json").write_text(json.dumps({"search_url": "https://duckduckgo.com/?q=%s"}))
    assert Store(tmp_path).search_url == "https://duckduckgo.com/?q=%s"


def test_unique_path(tmp_path):
    assert unique_path(tmp_path, "a.pdf") == tmp_path / "a.pdf"
    (tmp_path / "a.pdf").write_text("x")
    assert unique_path(tmp_path, "a.pdf") == tmp_path / "a (1).pdf"
    assert unique_path(tmp_path, "../../etc/passwd") == tmp_path / "passwd"
    assert unique_path(tmp_path, "") == tmp_path / "download"
