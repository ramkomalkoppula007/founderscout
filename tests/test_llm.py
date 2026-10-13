import pytest
from pydantic import BaseModel
from sqlalchemy import select

from founderscout.db import Step, session_scope
from founderscout.llm import LLM, BadOutput, extract_json


class Answer(BaseModel):
    number: int


def test_extract_json_ignores_fences_and_chatter():
    reply = 'Sure! Here it is:\n```json\n{"number": 4}\n```\nHope that helps.'
    assert extract_json(reply) == '{"number": 4}'


def test_extract_json_fails_when_there_is_no_object():
    with pytest.raises(ValueError):
        extract_json("I cannot help with that.")


def test_ask_repairs_a_bad_answer(monkeypatch):
    replies = iter(['{"number": "four"}', '{"number": 4}'])         # wrong type, then right
    seen = []

    def fake_chat(self, provider, model, agent, messages):
        seen.append(len(messages))
        return next(replies), 10, 5

    monkeypatch.setattr(LLM, "_chat", fake_chat)
    result = LLM().ask("fast", "test", "Answer.", "What is 2 + 2?", Answer)

    assert result.number == 4
    assert seen == [2, 4]           # second call carried the bad answer and the error
    with session_scope() as session:
        steps = session.scalars(select(Step).order_by(Step.id)).all()
    assert [step.ok for step in steps] == [False, True]


def test_ask_gives_up_after_one_repair(monkeypatch):
    monkeypatch.setattr(LLM, "_chat", lambda *args: ("not json at all", 1, 1))
    with pytest.raises(BadOutput):
        LLM().ask("fast", "test", "Answer.", "?", Answer)
