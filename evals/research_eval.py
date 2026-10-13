"""Eval 2: are the researched facts actually true? A human checks a sample.

The quote check proves a quote is on the page. It cannot prove that the claim
says the same thing as the quote. Only you can judge that, so this eval is
done by hand, and that is fine: a small honest hand-labelled number is worth
more than a large automatic one nobody checked.

    python -m evals.research_eval export   write facts to a CSV file
    (open the CSV, type y or n in the 'correct' column for each row, save)
    python -m evals.research_eval score    print the accuracy
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from sqlalchemy import select

from founderscout.db import Company, init_db, session_scope

CSV_PATH = Path(__file__).parent / "results" / "research_facts.csv"
COLUMNS = ["company", "claim", "quote", "source_url", "correct"]


def export(limit: int = 40) -> None:
    init_db()
    rows = []
    with session_scope() as session:
        for company in session.scalars(select(Company).where(Company.brief.is_not(None))
                                       .order_by(Company.id.desc())):
            for fact in company.brief["facts"]:
                rows.append([company.name, fact["claim"], fact["quote"],
                             fact["source_url"], ""])
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows[:limit])
    print(f"Wrote {min(len(rows), limit)} facts to {CSV_PATH}. Fill in the 'correct' column.")


def score() -> None:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        marks = [row["correct"].strip().lower() for row in csv.DictReader(handle)]
    judged = [mark for mark in marks if mark in {"y", "n"}]
    if not judged:
        raise SystemExit("No rows are marked y or n yet.")
    right = judged.count("y")
    print(f"Research accuracy: {right} of {len(judged)} facts correct "
          f"({100 * right / len(judged):.0f}%), judged by hand. Unmarked rows: "
          f"{len(marks) - len(judged)}.")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "export":
        export()
    elif command == "score":
        score()
    else:
        raise SystemExit(__doc__)
