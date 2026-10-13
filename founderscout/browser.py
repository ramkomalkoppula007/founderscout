"""The agent's "computer": a real Chromium browser with good manners.

Rules this browser always follows, whatever the model asks for:
  - only http and https, never private or local addresses (unless allowed for tests)
  - obey each site's robots.txt
  - say honestly who it is (User-Agent) and wait between page loads
  - never log in, never submit a form, never click: it only reads pages
"""
from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass
from urllib.parse import urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .config import get_settings
from .trace import log_step

BOT_NAME = "FounderScoutBot"
SKIP_FILES = (".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".mp4", ".webp")


class BrowserError(Exception):
    """The page could not be read (blocked, not allowed, too slow, 404...)."""


@dataclass
class PageData:
    url: str                      # final URL after redirects
    title: str
    text: str                     # visible text, trimmed
    links: list[tuple[str, str]]  # (link text, absolute url)


def is_private_host(host: str) -> bool:
    host = host.split(":")[0].lower()
    if host in {"localhost", ""} or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False               # a normal domain name
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


class PoliteBrowser:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.user_agent = f"{BOT_NAME}/0.1 (+{self.settings.bot_contact})"
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_load = 0.0

    # "with PoliteBrowser() as browser:" opens Chromium and always closes it.
    def __enter__(self) -> "PoliteBrowser":
        self._playwright = sync_playwright().start()
        self._chromium = self._playwright.chromium.launch(headless=True)
        self._context = self._chromium.new_context(user_agent=self.user_agent)
        # Do not download pictures, fonts or video: we only need the words.
        self._context.route("**/*", lambda route: route.abort()
                            if route.request.resource_type in {"image", "media", "font"}
                            else route.continue_())
        return self

    def __exit__(self, *_exc) -> None:
        self._context.close()
        self._chromium.close()
        self._playwright.stop()

    def check(self, url: str) -> None:
        """Raise BrowserError if this URL must not be opened."""
        parts = urlparse(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise BrowserError(f"not a web address: {url}")
        if is_private_host(parts.netloc) and not self.settings.allow_private_hosts:
            raise BrowserError(f"private address refused: {url}")
        if parts.path.lower().endswith(SKIP_FILES):
            raise BrowserError(f"not a web page: {url}")
        robots = self._robots_for(f"{parts.scheme}://{parts.netloc}")
        if robots and not robots.can_fetch(BOT_NAME, url):
            raise BrowserError(f"robots.txt does not allow: {url}")

    def _robots_for(self, origin: str) -> RobotFileParser | None:
        if origin not in self._robots:
            parser: RobotFileParser | None = None
            try:
                reply = httpx.get(origin + "/robots.txt", timeout=10, follow_redirects=True,
                                  headers={"User-Agent": self.user_agent})
                if reply.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(reply.text.splitlines())
                elif reply.status_code in (401, 403):  # "keep out" for everyone
                    parser = RobotFileParser()
                    parser.parse(["User-agent: *", "Disallow: /"])
            except httpx.HTTPError:
                parser = None      # no robots.txt reachable: nothing forbids us
            self._robots[origin] = parser
        return self._robots[origin]

    def fetch(self, url: str, company_id: int | None = None) -> PageData:
        """Open one page and return its text and links."""
        self.check(url)
        wait = self.settings.browser_delay - (time.time() - self._last_load)
        if wait > 0:
            time.sleep(wait)
        started = time.time()
        page = self._context.new_page()
        try:
            reply = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if reply is None or reply.status >= 400:
                raise BrowserError(f"HTTP {reply.status if reply else '?'} for {url}")
            self.check(page.url)              # a redirect may land somewhere else
            page.wait_for_timeout(1500)       # give JavaScript a moment to render
            text = re.sub(r"[ \t]+", " ", page.inner_text("body"))
            text = re.sub(r"\n\s*\n+", "\n", text).strip()[: self.settings.page_chars]
            raw_links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => [e.innerText.trim().slice(0, 60), e.href])")
            data = PageData(page.url, page.title(), text, self._clean_links(raw_links))
        except PlaywrightError as exc:
            log_step("browser", company_id=company_id, ok=False, note=f"{url} :: {exc}"[:300])
            raise BrowserError(f"could not load {url}") from exc
        except BrowserError as exc:
            log_step("browser", company_id=company_id, ok=False, note=str(exc))
            raise
        finally:
            page.close()
            self._last_load = time.time()
        log_step("browser", company_id=company_id, note=data.url,
                 ms=int((time.time() - started) * 1000))
        return data

    @staticmethod
    def _clean_links(raw_links: list[list[str]]) -> list[tuple[str, str]]:
        seen, links = set(), []
        for text, href in raw_links:
            href = urldefrag(href)[0]
            if href.startswith("http") and href not in seen:
                seen.add(href)
                links.append((" ".join(text.split()) or "(no text)", href))
        return links
