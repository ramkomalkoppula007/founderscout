"""The trace: one row for every model call and every page visit.

When a draft looks wrong, the trace tells you which step went wrong. It is
also where the cost and speed numbers on the stats page come from.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .db import Step, session_scope

_run_id = "manual"


def start_run() -> str:
    """Give this run a name, e.g. 20261008-013000. Every step is tagged with it."""
    global _run_id
    _run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return _run_id


def log_step(agent: str, *, company_id: int | None = None, model: str = "",
             tokens_in: int = 0, tokens_out: int = 0, ms: int = 0,
             ok: bool = True, note: str = "") -> None:
    with session_scope() as session:
        session.add(Step(run_id=_run_id, company_id=company_id, agent=agent,
                         model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                         ms=ms, ok=ok, note=note[:1000]))
