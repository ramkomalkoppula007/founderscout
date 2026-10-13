"""Numbers that describe how the system is really doing.

The same function feeds the /stats page and the table in your README.
Print the README table with: python -m founderscout.metrics
"""
from __future__ import annotations

from sqlalchemy import func, select

from .db import Company, Draft, Lesson, Step, init_db, session_scope


def _share(part: int, whole: int) -> str:
    """7 of 10 (70%)"""
    return f"{part} of {whole} ({100 * part / whole:.0f}%)" if whole else "n/a"


def collect() -> dict:
    with session_scope() as session:
        def count(model, *where) -> int:
            return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

        companies = count(Company)
        researched = count(Company, Company.brief.is_not(None))
        drafts = count(Draft)
        decided = count(Draft, Draft.status.in_(["approved", "sent", "rejected"]))
        approved = count(Draft, Draft.status.in_(["approved", "sent"]))
        untouched = count(Draft, Draft.status.in_(["approved", "sent"]),
                          Draft.edited.is_(False))
        first_pass = count(Draft, Draft.verdict == "pass", Draft.revisions == 0)
        flagged = count(Draft, Draft.verdict != "pass")
        proposed = kept = 0
        for brief in session.scalars(select(Company.brief).where(Company.brief.is_not(None))):
            proposed += brief.get("facts_proposed", 0)
            kept += brief.get("facts_kept", 0)
        tokens = session.scalar(select(func.sum(Step.tokens_in + Step.tokens_out))) or 0
        seconds = (session.scalar(select(func.sum(Step.ms))) or 0) / 1000
        model_calls = count(Step, Step.agent != "browser")
        pages = count(Step, Step.agent == "browser", Step.ok.is_(True))
        lessons = count(Lesson)

    return {
        "Posts the scout judged": companies,
        "Companies researched": researched,
        "Drafts written": drafts,
        "Facts with a verified quote": _share(kept, proposed),
        "Drafts that passed review first time": _share(first_pass, drafts),
        "Drafts still flagged after revisions": _share(flagged, drafts),
        "Drafts I approved": _share(approved, decided),
        "Approved without any edit": _share(untouched, approved),
        "Lessons learned from my edits": lessons,
        "Pages opened in the browser": pages,
        "Model calls": model_calls,
        "Tokens per draft (average)": round(tokens / drafts) if drafts else "n/a",
        "Seconds per draft (average)": round(seconds / drafts) if drafts else "n/a",
    }


if __name__ == "__main__":
    init_db()
    print("| Measure | Value |\n|---|---|")
    for name, value in collect().items():
        print(f"| {name} | {value} |")
