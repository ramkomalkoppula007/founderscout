"""The pipeline for ONE company, as a LangGraph state machine.

    research --> write --> review --+--> save --> END
        |          ^                |
        |          +--- revise -----+   (at most max_revisions times)
        +--> END (the site could not be researched)

Each node is a normal Python function: it reads the shared state and returns
only the keys it changed. The edges say what runs next. The loop from review
back to write is the reason to use a graph instead of a straight script.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .agents.research import ResearchError, research
from .agents.reviewer import review
from .agents.writer import write_draft
from .browser import PoliteBrowser
from .config import get_settings, load_profile
from .db import Company, Draft, session_scope
from .llm import LLM
from .memory import recent_lessons


class State(TypedDict, total=False):
    company_id: int
    brief: dict
    draft: dict
    review: dict
    revisions: int
    error: str


def build_graph(llm: LLM, browser: PoliteBrowser):
    settings = get_settings()
    profile = load_profile()

    def load(company_id: int) -> Company:
        with session_scope() as session:
            return session.get(Company, company_id)

    def research_node(state: State) -> State:
        company = load(state["company_id"])
        try:
            brief = research(llm, browser, company)
        except ResearchError as exc:
            with session_scope() as session:
                row = session.get(Company, company.id)
                row.status, row.note = "failed", str(exc)[:500]
            return {"error": str(exc)}
        with session_scope() as session:
            session.get(Company, company.id).brief = brief
        return {"brief": brief}

    def write_node(state: State) -> State:
        company = load(state["company_id"])
        last_review = state.get("review")
        notes = None
        if last_review:
            notes = last_review["issues"] + last_review["unsupported_claims"]
        draft = write_draft(llm, company, state["brief"], profile, recent_lessons(),
                            previous=state.get("draft"), notes=notes)
        revisions = state.get("revisions", 0) + (1 if last_review else 0)
        return {"draft": draft, "revisions": revisions}

    def review_node(state: State) -> State:
        company = load(state["company_id"])
        return {"review": review(llm, state["draft"], company, state["brief"], profile)}

    def save_node(state: State) -> State:
        with session_scope() as session:
            session.add(Draft(company_id=state["company_id"],
                              subject=state["draft"]["subject"][:300],
                              body=state["draft"]["body"],
                              verdict=state["review"]["verdict"],
                              review=state["review"],
                              revisions=state.get("revisions", 0)))
            session.get(Company, state["company_id"]).status = "drafted"
        return {}

    def after_research(state: State) -> str:
        return "stop" if state.get("error") else "write"

    def after_review(state: State) -> str:
        tries_left = state.get("revisions", 0) < settings.max_revisions
        if state["review"]["verdict"] == "revise" and tries_left:
            return "revise"
        return "save"      # passed, or out of attempts: a human decides either way

    graph = StateGraph(State)
    graph.add_node("research", research_node)
    graph.add_node("write", write_node)
    graph.add_node("review", review_node)
    graph.add_node("save", save_node)
    graph.add_edge(START, "research")
    graph.add_conditional_edges("research", after_research, {"write": "write", "stop": END})
    graph.add_edge("write", "review")
    graph.add_conditional_edges("review", after_review, {"revise": "write", "save": "save"})
    graph.add_edge("save", END)
    return graph.compile()
