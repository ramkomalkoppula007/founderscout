"""The exact shape of every answer we accept from a model.

A model returns text. These classes turn "some text" into data the rest of
the code can trust: wrong type, missing field or out-of-range number raises
an error instead of travelling silently through the pipeline.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScoutResult(BaseModel):
    company_name: str
    website: str | None = Field(default=None,
                                description="Company homepage URL if the post gives one")
    roles: list[str] = Field(default_factory=list, description="Job titles mentioned")
    remote_policy: Literal["worldwide", "restricted", "onsite", "unclear"]
    is_ai_company: bool
    contact: str | None = Field(default=None,
                                description="Email or link the post gives for applying")
    fit_score: int = Field(ge=0, le=100)
    fit_reason: str = Field(description="One sentence")


class NextStep(BaseModel):
    action: Literal["open", "stop"]
    url: str | None = Field(default=None,
                            description="Exactly one URL from LINKS when action is open")
    why: str


class Fact(BaseModel):
    claim: str = Field(description="One plain sentence about the company")
    quote: str = Field(description="Exact words copied from the page that prove the claim")
    source_url: str = Field(description="URL of the page the quote was copied from")


class Brief(BaseModel):
    what_they_build: str
    customers: str = Field(description="Who uses it, or 'not stated'")
    tech_stack: list[str] = Field(default_factory=list)
    founders: list[str] = Field(default_factory=list,
                                description="Full names exactly as written on a page")
    facts: list[Fact] = Field(description="3 to 6 facts, each with a quote")
    relevant_projects: list[str] = Field(
        default_factory=list, description="Names of the seeker's projects that relate")
    angle: str = Field(description="The most specific reason this seeker fits this company")


class DraftMessage(BaseModel):
    subject: str
    body: str


class Review(BaseModel):
    verdict: Literal["pass", "revise", "reject"]
    unsupported_claims: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class LessonOut(BaseModel):
    lesson: str = Field(description="One short general rule, or the single word none")
