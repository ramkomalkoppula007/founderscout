import pytest

from founderscout import config
from founderscout.browser import BrowserError, PoliteBrowser, is_private_host


def test_fetch_returns_text_and_links(site):
    with PoliteBrowser() as browser:
        page = browser.fetch(site + "/")
    assert "Brindle Loop builds AI support agents" in page.text
    assert page.title.startswith("Brindle Loop")
    assert ("About", site + "/about.html") in page.links


def test_robots_txt_is_obeyed(site):
    with PoliteBrowser() as browser:
        with pytest.raises(BrowserError, match="robots.txt"):
            browser.fetch(site + "/private/notes.html")


def test_missing_page_is_an_error(site):
    with PoliteBrowser() as browser:
        with pytest.raises(BrowserError):
            browser.fetch(site + "/no-such-page.html")


def test_private_addresses_are_refused_by_default(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_HOSTS", "false")
    config.get_settings.cache_clear()
    browser = PoliteBrowser()                # check() needs no running Chromium
    with pytest.raises(BrowserError, match="private address"):
        browser.check("http://127.0.0.1:8765/")
    with pytest.raises(BrowserError, match="not a web address"):
        browser.check("file:///etc/passwd")
    assert is_private_host("192.168.1.10") and is_private_host("localhost:3000")
    assert not is_private_host("example.com")
