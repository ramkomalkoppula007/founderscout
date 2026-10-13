"""End-to-end tests: saved posts -> scout -> browser -> brief -> draft -> review."""
import json

from sqlalchemy import select

from founderscout import llm as llm_module
from founderscout import run
from founderscout.db import Company, Draft, now, session_scope
from founderscout.fake_llm import fake_reply
from founderscout.llm import LLM
from founderscout.memory import learn_from_feedback, recent_lessons


def all_rows(model):
    with session_scope() as session:
        return session.scalars(select(model).order_by(model.id)).all()


def test_full_run_creates_one_reviewed_draft(site):
    assert run.main(["--source", "file"]) == 0

    companies = {company.name: company for company in all_rows(Company)}
    # two of the four posts pass the free keyword check
    assert set(companies) == {"Brindle Loop", "Quillmesh"}
    assert companies["Quillmesh"].status == "skipped"         # remote, but US only
    brindle = companies["Brindle Loop"]
    assert brindle.status == "drafted"
    assert brindle.brief["founders"] == ["Asha Verma", "Tomas Rey"]
    assert brindle.brief["facts_kept"] >= 2
    assert not any("/private/" in url for url in brindle.brief["pages"])

    (draft,) = all_rows(Draft)
    assert draft.status == "pending" and draft.verdict == "pass"
    assert draft.body.startswith("Hi Asha,")


def test_second_run_does_not_repeat_work(site):
    run.main(["--source", "file"])
    run.main(["--source", "file"])
    assert len(all_rows(Company)) == 2
    assert len(all_rows(Draft)) == 1


def test_reviewer_sends_a_bad_draft_back_once(site, monkeypatch):
    def writer_invents_funding(agent, messages):
        reply = json.loads(fake_reply(agent, messages))
        if agent == "writer" and "REVIEWER NOTES" not in messages[1]["content"]:
            reply["body"] = reply["body"].replace(
                "\n\nI built", " Congratulations on raising $40M.\n\nI built")
        return json.dumps(reply)

    monkeypatch.setattr(llm_module, "fake_reply", writer_invents_funding)
    run.main(["--source", "file"])

    (draft,) = all_rows(Draft)
    assert draft.revisions == 1 and draft.verdict == "pass"
    assert "$40M" not in draft.body


def test_fact_without_a_real_quote_is_dropped(site, monkeypatch):
    def brief_with_invented_fact(agent, messages):
        reply = json.loads(fake_reply(agent, messages))
        if agent == "research.brief":
            reply["facts"].append({
                "claim": "They raised a large round.",
                "quote": "We just closed our forty million dollar Series B",
                "source_url": reply["facts"][0]["source_url"]})
        return json.dumps(reply)

    monkeypatch.setattr(llm_module, "fake_reply", brief_with_invented_fact)
    run.main(["--source", "file"])

    brief = all_rows(Company)[0].brief
    assert brief["facts_kept"] == brief["facts_proposed"] - 1
    assert all("Series B" not in fact["quote"] for fact in brief["facts"])


def test_an_edit_becomes_a_lesson(site):
    run.main(["--source", "file"])
    with session_scope() as session:
        draft = session.scalars(select(Draft)).one()
        draft.final_body, draft.edited = "Hi Asha,\n\nShorter version.", True
        draft.status, draft.decided_at = "approved", now()

    assert learn_from_feedback(LLM()) == 1
    assert recent_lessons() == ["Keep the first line short and specific."]
    assert learn_from_feedback(LLM()) == 0         # the same edit is not learned twice
