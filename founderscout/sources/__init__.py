"""Where job posts come from. Every source returns the same RawPost shape,
so the scout does not care which one it is reading."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class RawPost:
    source: str                # "hn", "yc" or "file"
    source_id: str             # id inside that source, used to avoid repeats
    text: str                  # clean text, no HTML
    urls: list[str] = field(default_factory=list)


AI_WORDS = re.compile(r"\b(ai|llm|llms|agent|agents|agentic|genai|rag|machine learning)\b",
                      re.I)

# Links that are about applying, not the company's own site.
NOT_A_HOMEPAGE = ("linkedin.com", "greenhouse.io", "lever.co", "ashbyhq.com",
                  "workable.com", "notion.site", "notion.so", "docs.google.com",
                  "forms.gle", "ycombinator.com", "twitter.com", "x.com", "github.com",
                  "youtube.com", "calendly.com", "wellfound.com", "bit.ly")


def domain_of(url: str) -> str:
    """https://www.Example.com/jobs -> example.com"""
    return urlparse(url).netloc.lower().removeprefix("www.")


def looks_relevant(text: str) -> bool:
    """A free check before spending a model call: remote + something about AI."""
    return "remote" in text.lower() and bool(AI_WORDS.search(text))


def pick_homepage(urls: list[str]) -> str:
    """First link that is not a job board or a social profile."""
    for url in urls:
        host = domain_of(url)
        blocked = any(host == bad or host.endswith("." + bad) for bad in NOT_A_HOMEPAGE)
        if host and not blocked:
            return url
    return ""
