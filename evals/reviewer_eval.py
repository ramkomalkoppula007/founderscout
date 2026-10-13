"""Eval 1: does the reviewer catch errors that we plant on purpose?

Take a draft that is correct. Break it in one known way. Ask the reviewer.
If it still says "pass", the reviewer missed an error we know is there.

    python -m evals.reviewer_eval              built-in cases
    python -m evals.reviewer_eval --from-db    your own approved drafts

Two numbers come out:
  catch rate    planted errors that were flagged (higher is better)
  false alarms  clean drafts that were flagged   (lower is better)
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from founderscout.agents.reviewer import review
from founderscout.config import get_settings, load_profile
from founderscout.db import Company, Draft, init_db, session_scope
from founderscout.llm import LLM

HERE = Path(__file__).parent


def after_greeting(body: str, sentence: str) -> str:
    """Insert a sentence at the start of the first paragraph after 'Hi X,'."""
    greeting, _, rest = body.partition("\n\n")
    return f"{greeting}\n\n{sentence} {rest}"


# name of the error -> function that damages a correct draft
PLANTS = {
    "invented funding": lambda body, company: after_greeting(
        body, "Congratulations on closing your $40M Series B last month."),
    "invented customers": lambda body, company: after_greeting(
        body, "I saw that three of the ten largest banks in Europe already use it."),
    "invented sender claim": lambda body, company: after_greeting(
        body, "I spent six years leading the agents team at a large AI lab."),
    "wrong company name": lambda body, company: body.replace(company, "Northwind Robotics"),
    "placeholder left in": lambda body, company: (
        "Hi [Founder name],\n\n" + body.partition("\n\n")[2]),
    "unknown link": lambda body, company: after_greeting(
        body, "My portfolio is at https://my-portfolio.example/work."),
}


def clean_draft(case: dict, profile: dict) -> dict:
    """A correct message for this case, built from YOUR profile."""
    project = profile["projects"][0]
    founders = case["founders"]
    greeting = founders[0].split()[0] if founders else f"{case['company']} team"
    body = (f"Hi {greeting},\n\n{case['opening']}\n\n"
            f"I built {project['name']}: {project['one_line']} {project['url']}\n\n"
            f"{profile['ask']} I am based in {profile['location']}.\n\n"
            f"{profile['signature']}")
    return {"subject": f"Agent engineer for {case['company']}", "body": body}


def cases_from_db() -> list[tuple[Company, dict, dict]]:
    with session_scope() as session:
        drafts = session.scalars(select(Draft).options(joinedload(Draft.company))
                                 .where(Draft.status.in_(["approved", "sent"]))).all()
    return [(d.company, d.company.brief, {"subject": d.subject, "body": d.final_body})
            for d in drafts]


def cases_from_file(profile: dict) -> list[tuple[Company, dict, dict]]:
    cases = json.loads((HERE / "review_cases.json").read_text(encoding="utf-8"))
    return [(Company(name=c["company"], domain=c["domain"]),
             {"facts": c["facts"], "founders": c["founders"]},
             clean_draft(c, profile)) for c in cases]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-db", action="store_true")
    args = parser.parse_args()
    init_db()
    settings, profile, llm = get_settings(), load_profile(), LLM()
    cases = cases_from_db() if args.from_db else cases_from_file(profile)
    if not cases:
        raise SystemExit("No cases. Approve some drafts first, or run without --from-db.")

    false_alarms = 0
    caught = {name: 0 for name in PLANTS}
    for company, brief, draft in cases:
        if review(llm, draft, company, brief, profile)["verdict"] != "pass":
            false_alarms += 1
        for name, damage in PLANTS.items():
            broken = {**draft, "body": damage(draft["body"], company.name)}
            if review(llm, broken, company, brief, profile)["verdict"] != "pass":
                caught[name] += 1

    total, n = sum(caught.values()), len(cases)
    model = "fake model" if settings.llm_mode == "fake" else settings.model_review
    lines = [f"# Reviewer eval, {date.today()}", "",
             f"Reviewer: `{model}` plus rule checks. Cases: {n}"
             f" ({'my approved drafts' if args.from_db else 'built-in'}).", "",
             "| Planted error | Caught |", "|---|---|"]
    lines += [f"| {name} | {hits} of {n} |" for name, hits in caught.items()]
    planted = n * len(PLANTS)
    lines += ["", f"**Catch rate: {total} of {planted} ({100 * total / planted:.0f}%)**",
              "", f"**False alarms on clean drafts: {false_alarms} of {n}**", ""]
    report = "\n".join(lines)
    (HERE / "results" / "reviewer_eval.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
