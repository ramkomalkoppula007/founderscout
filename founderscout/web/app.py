"""The approval inbox: the human-in-the-loop part.

This small site only reads and writes the database. It never calls a model
and never opens a browser, so it runs on the smallest free server.

    uvicorn founderscout.web.app:app --reload
"""
from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from ..config import get_settings
from ..db import Company, Draft, Lesson, Step, init_db, now, session_scope
from ..metrics import collect

HERE = Path(__file__).parent
app = FastAPI(title="FounderScout", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")  # escapes HTML by default
basic = HTTPBasic()
init_db()

TABS = ["pending", "approved", "sent", "rejected"]


def current_user(credentials: HTTPBasicCredentials = Depends(basic)) -> str:
    """Two logins: admin can decide, viewer can only look. Returns the role."""
    settings = get_settings()
    passwords = {"admin": settings.admin_password, "viewer": settings.viewer_password}
    expected = passwords.get(credentials.username, "")
    # compare_digest takes the same time for right and wrong guesses
    if expected and secrets.compare_digest(credentials.password.encode(), expected.encode()):
        return credentials.username
    raise HTTPException(401, "Wrong user name or password",
                        headers={"WWW-Authenticate": "Basic"})


def admin_only(request: Request, user: str = Depends(current_user)) -> str:
    if user != "admin":
        raise HTTPException(403, "The viewer login cannot change anything")
    # A form on another website must not be able to press our buttons.
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Request came from another site")
    return user


def get_draft(session, draft_id: int) -> Draft:
    draft = session.scalar(select(Draft).options(joinedload(Draft.company))
                           .where(Draft.id == draft_id))
    if not draft:
        raise HTTPException(404, "No such draft")
    return draft


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def inbox(request: Request, tab: str = "pending", user: str = Depends(current_user)):
    tab = tab if tab in TABS else "pending"
    with session_scope() as session:
        drafts = session.scalars(select(Draft).options(joinedload(Draft.company))
                                 .where(Draft.status == tab).order_by(Draft.id.desc())).all()
        counts = {name: session.scalar(select(func.count()).select_from(Draft)
                                       .where(Draft.status == name))
                  for name in TABS}
    return templates.TemplateResponse(request, "inbox.html", {
        "drafts": drafts, "tab": tab, "tabs": TABS, "counts": counts, "user": user})


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_page(request: Request, draft_id: int, user: str = Depends(current_user)):
    with session_scope() as session:
        draft = get_draft(session, draft_id)
        steps = session.scalars(select(Step).where(Step.company_id == draft.company_id)
                                .order_by(Step.id)).all()
    return templates.TemplateResponse(request, "draft.html", {
        "draft": draft, "company": draft.company, "brief": draft.company.brief or {},
        "review": draft.review or {}, "steps": steps, "user": user})


@app.post("/drafts/{draft_id}/approve")
def approve(draft_id: int, subject: str = Form(...), body: str = Form(...),
            _user: str = Depends(admin_only)):
    body = body.replace("\r\n", "\n").strip()
    with session_scope() as session:
        draft = get_draft(session, draft_id)
        draft.edited = body != draft.body.strip()     # did the human change it?
        draft.final_body, draft.subject = body, subject.strip()[:300]
        draft.status, draft.decided_at = "approved", now()
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@app.post("/drafts/{draft_id}/reject")
def reject(draft_id: int, reason: str = Form(""), _user: str = Depends(admin_only)):
    with session_scope() as session:
        draft = get_draft(session, draft_id)
        draft.status, draft.reject_reason = "rejected", reason.strip()
        draft.decided_at = now()
    return RedirectResponse("/", status_code=303)


@app.post("/drafts/{draft_id}/sent")
def mark_sent(draft_id: int, _user: str = Depends(admin_only)):
    """You send the message yourself, then record it here. The agent never sends."""
    with session_scope() as session:
        draft = get_draft(session, draft_id)
        if draft.status != "approved":
            raise HTTPException(400, "Only an approved draft can be marked as sent")
        draft.status = "sent"
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, user: str = Depends(current_user)):
    with session_scope() as session:
        lessons = session.scalars(select(Lesson).order_by(Lesson.id.desc()).limit(20)).all()
        skipped = session.scalars(select(Company)
                                  .where(Company.status.in_(["skipped", "failed"]))
                                  .order_by(Company.id.desc()).limit(15)).all()
    return templates.TemplateResponse(request, "stats.html", {
        "metrics": collect(), "lessons": lessons, "skipped": skipped, "user": user})
