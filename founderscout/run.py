"""The daily run. This is what GitHub Actions starts every morning.

    python -m founderscout.run                     Hacker News, real or fake model
    python -m founderscout.run --source file       saved posts, no network needed
    python -m founderscout.run --max 2             only two companies
"""
from __future__ import annotations

import argparse

import httpx
from sqlalchemy import select

from .agents.scout import scout
from .browser import PoliteBrowser
from .config import ROOT, get_settings
from .db import Company, init_db, session_scope
from .graph import build_graph
from .llm import LLM, BadOutput, QuotaExhausted
from .memory import learn_from_feedback
from .sources import hn, yc
from .trace import start_run


def get_posts(source: str, file: str):
    if source == "file":
        return hn.posts_from_file(file)
    if source == "yc":
        return yc.fetch_posts()
    return hn.fetch_posts()


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Find, research and draft.")
    parser.add_argument("--source", choices=["hn", "yc", "file"], default="hn")
    parser.add_argument("--file", default=str(ROOT / "tests" / "fixtures" / "hn_posts.json"))
    parser.add_argument("--max", type=int, default=settings.max_companies,
                        help="how many companies to research in this run")
    args = parser.parse_args(argv)

    profile_text = settings.profile_path.read_text(encoding="utf-8")
    if settings.llm_mode == "real" and "YOUR_" in profile_text:
        print("Fill in my_profile.json first: it still contains YOUR_ placeholders.")
        return 1

    init_db()
    run_id = start_run()
    llm = LLM()
    print(f"Run {run_id} | model mode: {settings.llm_mode} | source: {args.source}")

    try:
        print(f"Lessons learned from your feedback: {learn_from_feedback(llm)}")
        posts = get_posts(args.source, args.file)
        print(f"Posts fetched: {len(posts)}")
        print(f"New companies worth researching: {scout(llm, posts)}")
    except QuotaExhausted as exc:
        print(f"Stopped early: {exc}")         # research what we already have
    except httpx.HTTPError as exc:
        print(f"Could not fetch posts: {exc}")  # same: carry on with leftovers

    # Best fit first. Companies left over from earlier days are picked up too.
    with session_scope() as session:
        todo = session.scalars(select(Company).where(Company.status == "new")
                               .order_by(Company.fit_score.desc()).limit(args.max)).all()

    drafted = failed = 0
    with PoliteBrowser() as browser:
        graph = build_graph(llm, browser)
        for company in todo:
            print(f"- {company.name} (fit {company.fit_score}) ... ", end="", flush=True)
            try:
                final = graph.invoke({"company_id": company.id, "revisions": 0})
            except QuotaExhausted as exc:
                print(f"stopped: {exc}")
                break                           # the company stays "new" for tomorrow
            except BadOutput as exc:
                with session_scope() as session:
                    row = session.get(Company, company.id)
                    row.status, row.note = "failed", str(exc)[:500]
                final = {"error": "the model returned unusable output"}
            if final.get("error"):
                failed += 1
                print(f"failed: {final['error']}")
            else:
                drafted += 1
                print(f"draft saved (review: {final['review']['verdict']}, "
                      f"revisions: {final.get('revisions', 0)})")

    print(f"Done. Drafts waiting for you: {drafted}. Failed: {failed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
