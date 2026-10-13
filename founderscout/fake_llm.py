"""A pretend model for building and testing without API keys.

With LLM_MODE=fake, LLM.ask() calls fake_reply() instead of a real provider.
The answers are simple and predictable, which is exactly what tests need:
the same input always gives the same output, instantly, for free.

It reads the same prompt a real model would get, so it also proves that the
prompts contain the information each agent needs.
"""
from __future__ import annotations

import json
import re

URL = re.compile(r"https?://[^\s\"'<>)|]+")


def _line(text: str, label: str) -> str:
    """Value of a 'LABEL: value' line, or ''."""
    match = re.search(rf"^{label}:[ \t]*(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _after(text: str, label: str) -> str:
    """Everything after a 'LABEL:' line."""
    return text.split(f"{label}:", 1)[1] if f"{label}:" in text else ""


def _scout(user: str) -> dict:
    post = _after(user, "JOB POST").strip()
    low = post.lower()
    name = post.split("|")[0].strip()[:80] or "Unknown"
    urls = URL.findall(post)
    if "onsite" in low or "on-site" in low:
        policy, score = "onsite", 10
    elif "worldwide" in low or "anywhere" in low:
        policy, score = "worldwide", 85
    elif "remote" in low:
        policy, score = "restricted", 40
    else:
        policy, score = "unclear", 30
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", post)
    return {"company_name": name, "website": urls[0] if urls else None,
            "roles": ["AI Engineer"], "remote_policy": policy,
            "is_ai_company": bool(re.search(r"\b(ai|llm|agents?)\b", low)),
            "contact": email.group(0) if email else None,
            "fit_score": score, "fit_reason": f"Fake scout: remote policy is {policy}."}


def _pick(user: str) -> dict:
    visited = _after(user, "VISITED").split("LINKS:")[0]
    links = [line.rsplit("|", 1)[-1].strip() for line in _after(user, "LINKS").splitlines()
             if "|" in line]
    for word in ("about", "team", "careers", "jobs", "blog"):
        for link in links:
            if word in link.lower() and link not in visited:
                return {"action": "open", "url": link, "why": f"Fake pick: {word} page."}
    return {"action": "stop", "url": None, "why": "Fake pick: nothing useful left."}


def _brief(user: str) -> dict:
    facts, founders = [], []
    for block in user.split("=== PAGE ")[1:]:
        url, _, text = block.partition(" ===")
        # first long line = first real paragraph (skips menus and headings)
        paragraphs = [line.strip() for line in text.splitlines() if len(line.strip()) > 60]
        if paragraphs:
            sentence = re.split(r"(?<=[.!?])\s+", paragraphs[0])[0]
            facts.append({"claim": sentence, "quote": sentence, "source_url": url.strip()})
        found = re.search(r"by ([A-Z]\w+ [A-Z]\w+) and ([A-Z]\w+ [A-Z]\w+)", text)
        if found:
            founders = [found.group(1), found.group(2)]
    projects = re.findall(r"^- ([\w-]+):", _after(user, "SEEKER PROJECTS"), re.MULTILINE)
    first = facts[0]["claim"] if facts else "not stated"
    return {"what_they_build": first, "customers": "not stated", "tech_stack": [],
            "founders": founders, "facts": facts[:6], "relevant_projects": projects[:1],
            "angle": "Fake brief: the seeker has built a similar agent."}


def _writer(user: str) -> dict:
    company = _line(user, "COMPANY")
    founders = _line(user, "FOUNDERS")
    known = founders and founders != "unknown"
    greeting = founders.split(",")[0].split()[0] if known else f"{company} team"
    fact = re.search(r"^1\. (.*)$", _after(user, "FACTS"), re.MULTILINE)
    profile = json.loads(_after(user, "SENDER PROFILE").split("LESSONS:")[0])
    project = profile["projects"][0]
    body = (f"Hi {greeting},\n\n"
            f"I read this on the {company} site: {fact.group(1) if fact else ''}\n\n"
            f"I built {project['name']}, which is close to that work: {project['url']}\n\n"
            f"{profile['ask']} I am based in {profile['location']}.\n\n"
            f"{profile['signature']}")
    return {"subject": f"Engineer who builds agents, for {company}", "body": body}


def _reviewer(user: str) -> dict:
    facts = _after(user, "FACTS").split("SENDER PROFILE:")[0]
    body = _after(user, "DRAFT BODY")
    if "$" in body and "$" not in facts:
        return {"verdict": "revise", "issues": [],
                "unsupported_claims": ["The draft mentions money that no fact supports."]}
    return {"verdict": "pass", "unsupported_claims": [], "issues": []}


def fake_reply(agent: str, messages: list[dict]) -> str:
    user = messages[1]["content"]
    handlers = {"scout": _scout, "research.pick": _pick, "research.brief": _brief,
                "writer": _writer, "reviewer": _reviewer,
                "memory": lambda _u: {"lesson": "Keep the first line short and specific."}}
    return json.dumps(handlers[agent](user))
