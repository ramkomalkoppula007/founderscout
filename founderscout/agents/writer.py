"""Writer: turn a verified brief into one short message.

The writer never sees the web pages. It sees only facts that passed the quote
check, so the easiest way for it to write something true is to use them.
"""
from __future__ import annotations

import json

from ..db import Company
from ..llm import LLM
from ..schemas import DraftMessage

SYSTEM = """You write a first message from a job seeker to the founders of a small startup.

Hard rules:
- 80 to 130 words in the body. Plain text only: no markdown, no bullet points, no emojis.
- Greeting: "Hi <first name>," if FOUNDERS gives a name, otherwise "Hi <Company> team,".
- First sentence: one specific observation about the company, taken ONLY from FACTS.
- Then connect ONE project from SENDER PROFILE to that work, and include its URL.
- Then the ask from SENDER PROFILE, and where the sender is based.
- End with the signature from SENDER PROFILE, exactly as given.
- Say nothing about the company that is not in FACTS. No guesses about funding,
  customers, growth or plans.
- Say nothing about the sender that is not in SENDER PROFILE. No invented numbers.
- Do not use these words: impressed, amazing, excited, passionate, love, thrilled.
- Follow every line under LESSONS. They come from the sender's own edits.

If PREVIOUS DRAFT and REVIEWER NOTES are given, fix every note and keep what was fine.
The subject line is under 9 words and names something specific, not "Job application"."""


def write_draft(llm: LLM, company: Company, brief: dict, profile: dict,
                lessons: list[str], previous: dict | None = None,
                notes: list[str] | None = None) -> dict:
    facts = "\n".join(f"{i}. {fact['claim']}" for i, fact in enumerate(brief["facts"], 1))
    user = (f"COMPANY: {company.name}\n"
            f"ROLES: {company.roles or 'not stated'}\n"
            f"FOUNDERS: {', '.join(brief['founders']) or 'unknown'}\n"
            f"WHAT THEY BUILD: {brief['what_they_build']}\n"
            f"ANGLE: {brief['angle']}\n"
            f"FACTS:\n{facts}\n"
            f"SENDER PROFILE:\n{json.dumps(profile, indent=1)}\n"
            "LESSONS:\n" + ("\n".join(f"- {text}" for text in lessons) or "- none yet"))
    if previous:
        user += (f"\nPREVIOUS DRAFT:\n{previous['body']}\n"
                 "REVIEWER NOTES:\n" + "\n".join(f"- {note}" for note in notes or []))
    draft: DraftMessage = llm.ask("smart", "writer", SYSTEM, user, DraftMessage, company.id)
    return {"subject": draft.subject.strip(), "body": draft.body.strip()}
