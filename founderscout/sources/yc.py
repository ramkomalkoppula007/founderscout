"""Optional second source: Y Combinator companies that are hiring.

This reads the open "yc-oss" dataset, an unofficial JSON copy of YC's public
company directory. It is a community project, so it can be out of date or
disappear. That is why Hacker News is the main source and this one is extra.
"""
from __future__ import annotations

import httpx

from . import AI_WORDS, RawPost

URL = "https://yc-oss.github.io/api/companies/hiring.json"


def post_from_company(company: dict) -> RawPost | None:
    """Turn one directory entry into the same text shape as an HN job post."""
    regions = company.get("regions") or []
    tags = ", ".join(company.get("tags") or [])
    description = company.get("long_description") or company.get("one_liner") or ""
    if "Remote" not in regions or not company.get("website"):
        return None
    if not AI_WORDS.search(f"{tags} {description}"):
        return None
    text = (f"{company['name']} | {' / '.join(regions)} | YC {company.get('batch', '')} | "
            f"team of {company.get('team_size', '?')} | hiring\n\n"
            f"{company.get('one_liner', '')}\n\n{description}\n\nTags: {tags}\n"
            f"Remote regions listed: {', '.join(regions)}")
    return RawPost("yc", str(company["id"]), text, [company["website"]])


def fetch_posts(limit: int = 200) -> list[RawPost]:
    with httpx.Client(timeout=30, headers={"User-Agent": "FounderScoutBot/0.1"}) as client:
        reply = client.get(URL)
        reply.raise_for_status()
    # newest companies first: they are the ones still building their team
    companies = sorted(reply.json(), key=lambda c: c.get("launched_at") or 0, reverse=True)
    posts = [post_from_company(c) for c in companies[:limit]]
    return [p for p in posts if p]
