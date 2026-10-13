import pytest
from fastapi.testclient import TestClient

from founderscout.db import Company, Draft, session_scope

ADMIN, VIEWER = ("admin", "secret"), ("viewer", "look")


@pytest.fixture
def client():
    from founderscout.web.app import app      # imported here, after test settings exist
    with session_scope() as session:
        company = Company(source="file", source_id="1", name="Brindle Loop",
                          website="http://127.0.0.1:8765/", domain="127.0.0.1:8765",
                          fit_score=85, brief={"what_they_build": "Support agents",
                                               "facts": [], "founders": []})
        session.add(company)
        session.flush()                       # gives company.id before commit
        session.add(Draft(company_id=company.id, subject="Hello",
                          body="Hi Brindle Loop team,", verdict="pass",
                          review={"checked_by": "model"}))
    return TestClient(app, follow_redirects=False)


def draft_row() -> Draft:
    with session_scope() as session:
        return session.get(Draft, 1)


def test_pages_need_a_login(client):
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("admin", "wrong")).status_code == 401
    assert client.get("/healthz").status_code == 200      # for uptime checks only


def test_viewer_can_look_but_not_decide(client):
    assert "Brindle Loop" in client.get("/", auth=VIEWER).text
    assert client.get("/drafts/1", auth=VIEWER).status_code == 200
    reply = client.post("/drafts/1/approve", auth=VIEWER, data={"subject": "x", "body": "y"})
    assert reply.status_code == 403
    assert draft_row().status == "pending"


def test_approve_records_whether_the_human_edited(client):
    reply = client.post("/drafts/1/approve", auth=ADMIN,
                        data={"subject": "Hello", "body": "Hi Brindle Loop team, shorter."})
    assert reply.status_code == 303
    draft = draft_row()
    assert draft.status == "approved" and draft.edited is True
    assert draft.final_body == "Hi Brindle Loop team, shorter."

    assert client.post("/drafts/1/sent", auth=ADMIN).status_code == 303
    assert draft_row().status == "sent"


def test_reject_keeps_the_reason(client):
    client.post("/drafts/1/reject", auth=ADMIN, data={"reason": "Too generic"})
    draft = draft_row()
    assert draft.status == "rejected" and draft.reject_reason == "Too generic"


def test_a_form_on_another_site_cannot_approve(client):
    reply = client.post("/drafts/1/approve", auth=ADMIN,
                        headers={"Origin": "https://evil.example"},
                        data={"subject": "x", "body": "y"})
    assert reply.status_code == 403
    assert draft_row().status == "pending"


def test_stats_page_renders(client):
    assert "Drafts written" in client.get("/stats", auth=ADMIN).text
