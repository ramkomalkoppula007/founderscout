"""One small door to every model.

Gemini and Groq both speak the OpenAI chat format, so one client library
(openai) works for both: only the base URL and the key change.

Every agent calls LLM.ask(). It gives back a validated Pydantic object, or
raises. Nothing else in the project talks to a model directly, so limits,
retries, JSON repair and tracing live in exactly one place.
"""
from __future__ import annotations

import json
import time

import openai
from pydantic import BaseModel, ValidationError

from .config import get_settings
from .fake_llm import fake_reply
from .trace import log_step

PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key": "gemini_api_key",
        "gap": "gemini_gap",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key": "groq_api_key",
        "gap": "groq_gap",
    },
}


class QuotaExhausted(Exception):
    """The free limit for today (or this minute) is used up. Stop the run."""


class BadOutput(Exception):
    """The model could not produce valid JSON even after one repair attempt."""


def extract_json(text: str) -> str:
    """Models sometimes wrap JSON in ``` fences or add a sentence. Cut it out."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the model reply")
    return text[start:end + 1]


class LLM:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._clients: dict[str, openai.OpenAI] = {}
        self._last_call: dict[str, float] = {}
        self._json_mode: dict[str, bool] = {}

    # ---- public -----------------------------------------------------------
    def ask(self, role: str, agent: str, system: str, user: str,
            schema: type[BaseModel], company_id: int | None = None) -> BaseModel:
        """role picks the model (fast / smart / review). agent names the trace row."""
        provider, model = self._route(role)
        system += ("\n\nReply with ONE JSON object and nothing else. No markdown. "
                   "It must match this JSON schema:\n"
                   + json.dumps(schema.model_json_schema()))
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        problem = ""
        for _attempt in range(2):                      # first try + one repair
            started = time.time()
            text, t_in, t_out = self._chat(provider, model, agent, messages)
            ms = int((time.time() - started) * 1000)
            try:
                result = schema.model_validate_json(extract_json(text))
            except (ValidationError, ValueError) as exc:
                problem = str(exc)[:600]
                log_step(agent, company_id=company_id, model=model, tokens_in=t_in,
                         tokens_out=t_out, ms=ms, ok=False, note="bad JSON: " + problem)
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "That did not match the schema. Error:\n"
                     + problem + "\nSend the corrected JSON object only."},
                ]
                continue
            log_step(agent, company_id=company_id, model=model,
                     tokens_in=t_in, tokens_out=t_out, ms=ms)
            return result
        raise BadOutput(f"{agent}: no valid JSON after a repair attempt: {problem}")

    # ---- internals --------------------------------------------------------
    def _route(self, role: str) -> tuple[str, str]:
        if self.settings.llm_mode == "fake":
            return "fake", "fake"
        provider, _, model = getattr(self.settings, f"model_{role}").partition(":")
        if provider not in PROVIDERS or not model:
            raise RuntimeError(f"MODEL_{role.upper()} must look like provider:model")
        return provider, model

    def _client(self, provider: str) -> openai.OpenAI:
        if provider not in self._clients:
            info = PROVIDERS[provider]
            key = getattr(self.settings, info["key"])
            if not key:
                raise RuntimeError(f"{info['key'].upper()} is empty. Put it in .env "
                                   "(or set LLM_MODE=fake to work without keys).")
            # max_retries: the library itself waits and retries on 429 and 5xx.
            self._clients[provider] = openai.OpenAI(
                api_key=key, base_url=info["base_url"], max_retries=4, timeout=90)
        return self._clients[provider]

    def _wait(self, provider: str) -> None:
        """Free tiers limit calls per minute. Keep a minimum gap between calls."""
        gap = getattr(self.settings, PROVIDERS[provider]["gap"])
        since = time.time() - self._last_call.get(provider, 0.0)
        if since < gap:
            time.sleep(gap - since)
        self._last_call[provider] = time.time()

    def _chat(self, provider: str, model: str, agent: str,
              messages: list[dict]) -> tuple[str, int, int]:
        if provider == "fake":
            text = fake_reply(agent, messages)
            chars = sum(len(m["content"]) for m in messages)
            return text, chars // 4, len(text) // 4       # rough token estimate
        self._wait(provider)
        client = self._client(provider)
        kwargs: dict = {"model": model, "messages": messages}
        if self._json_mode.get(provider, True):
            kwargs["response_format"] = {"type": "json_object"}
        try:
            try:
                response = client.chat.completions.create(**kwargs)
            except openai.BadRequestError:
                if "response_format" not in kwargs:
                    raise
                # This provider/model refused JSON mode. Ask again without it;
                # extract_json() and the schema check still protect us.
                self._json_mode[provider] = False
                response = client.chat.completions.create(model=model, messages=messages)
        except openai.RateLimitError as exc:
            raise QuotaExhausted(f"{provider}: rate limit or daily quota reached") from exc
        usage = response.usage
        return (response.choices[0].message.content or "",
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0)
