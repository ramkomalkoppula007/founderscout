"""Hacker News "Ask HN: Who is hiring?" through the public HN Search API.

Why an API and not the browser here: HN publishes this API for programs to
use. It is faster, lighter for them, and gives clean data. The browser is
kept for company websites, where no API exists.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import httpx

from . import RawPost

API = "https://hn.algolia.com/api/v1"
HREF = re.compile(r'href="([^"]+)"')
TAG = re.compile(r"<[^>]+>")


def clean_html(comment_html: str) -> tuple[str, list[str]]:
    """HN stores comments as HTML. Return plain text and the links inside it."""
    urls = [html.unescape(u) for u in HREF.findall(comment_html)]
    text = comment_html.replace("<p>", "\n\n")
    text = html.unescape(TAG.sub("", text))
    return text.strip(), urls


def posts_from_hits(hits: list[dict], story_id: int) -> list[RawPost]:
    """Keep top-level comments only. Replies are discussion, not job posts."""
    posts = []
    for hit in hits:
        if str(hit.get("parent_id")) != str(story_id) or not hit.get("comment_text"):
            continue
        text, urls = clean_html(hit["comment_text"])
        posts.append(RawPost("hn", str(hit["objectID"]), text, urls))
    return posts


def latest_thread_id(client: httpx.Client) -> int:
    """The newest monthly thread. The account 'whoishiring' posts three kinds;
    we want the one whose title starts with 'Ask HN: Who is hiring?'."""
    reply = client.get(f"{API}/search_by_date",
                       params={"tags": "story,author_whoishiring", "hitsPerPage": 10})
    reply.raise_for_status()
    for hit in reply.json()["hits"]:
        if hit["title"].startswith("Ask HN: Who is hiring?"):
            return int(hit["objectID"])
    raise RuntimeError("Could not find a 'Who is hiring?' thread")


def fetch_posts(max_pages: int = 5) -> list[RawPost]:
    """Newest posts first. 100 comments per page; a thread has a few hundred."""
    posts: list[RawPost] = []
    with httpx.Client(timeout=30, headers={"User-Agent": "FounderScoutBot/0.1"}) as client:
        story_id = latest_thread_id(client)
        for page in range(max_pages):
            reply = client.get(f"{API}/search_by_date",
                               params={"tags": f"comment,story_{story_id}",
                                       "hitsPerPage": 100, "page": page})
            reply.raise_for_status()
            data = reply.json()
            posts += posts_from_hits(data["hits"], story_id)
            if page + 1 >= data["nbPages"]:
                break
    return posts


def posts_from_file(path: str | Path) -> list[RawPost]:
    """A saved API reply. Lets you develop and test with no network at all."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    posts = posts_from_hits(data["hits"], data["story_id"])
    return [RawPost("file", p.source_id, p.text, p.urls) for p in posts]
