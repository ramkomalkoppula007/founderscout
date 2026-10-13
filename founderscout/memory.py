"""Memory that makes tomorrow's drafts better than today's.

When you edit a draft before approving it, or reject one with a reason, that
is a free lesson about how you want to sound. This module turns each of those
into one short rule and stores it. The writer reads the newest rules on every
run.

(The other memory, "have I already seen this company", is simply the
companies table: the scout checks it before doing any work.)
"""
from __future__ import annotations

from sqlalchemy import select

from .db import Draft, Lesson, session_scope
from .llm import LLM
from .schemas import LessonOut

SYSTEM = """A job seeker changed or rejected a message an assistant drafted for them.
Work out what the assistant should do differently next time, for ANY company.
Write ONE rule of at most 20 words, starting with a verb. Example:
"Name the project in the second sentence, before describing it."
Do not mention this particular company or person.
If the change is trivial (a typo, a comma) answer with the single word: none"""


def recent_lessons(limit: int = 8) -> list[str]:
    with session_scope() as session:
        rows = session.scalars(select(Lesson).order_by(Lesson.id.desc()).limit(limit)).all()
        return [row.text for row in reversed(rows)]


def learn_from_feedback(llm: LLM) -> int:
    """Turn new edits and rejections into lessons. Returns how many were added."""
    with session_scope() as session:
        todo = session.scalars(select(Draft).where(
            Draft.lesson_done.is_(False),
            ((Draft.edited.is_(True)) & (Draft.status.in_(["approved", "sent"])))
            | ((Draft.status == "rejected") & (Draft.reject_reason != "")))).all()
    added = 0
    for draft in todo:
        if draft.status == "rejected":
            user = f"REJECTED DRAFT:\n{draft.body}\n\nREASON: {draft.reject_reason}"
        else:
            user = f"ORIGINAL:\n{draft.body}\n\nEDITED:\n{draft.final_body}"
        result: LessonOut = llm.ask("fast", "memory", SYSTEM, user, LessonOut,
                                    draft.company_id)
        text = result.lesson.strip()
        with session_scope() as session:
            if text and text.lower().strip(".") != "none":
                session.add(Lesson(text=text[:300], draft_id=draft.id))
                added += 1
            session.get(Draft, draft.id).lesson_done = True
    return added
