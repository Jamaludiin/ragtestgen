"""Uniform chat-completion client over Groq and OpenRouter.

Both providers are used on free tiers, whose limits shape the client:

  * Groq enforces per-minute token budgets (TPM/ITPM/OTPM) and reports exactly
    how long to wait, so 429s are transient and worth honouring precisely.
  * OpenRouter free models enforce a per-day request cap, which no amount of
    waiting inside a run will clear; that is raised as a terminal error rather
    than retried.

Requests to one model are serialised so that concurrent program/model workers
do not race each other into the same per-minute budget.
"""
import json, re, threading, time

import requests

from .config import PROVIDERS

TIMEOUT = 180
# Groq's per-day token cap recovers on a rolling window and can ask for waits of
# several minutes. Requests are gated per model, so waiting one out stalls only
# that model rather than the run.
MAX_SLEEP = 450         # cap on an honoured retry-after, seconds

_gates = {}
_gates_lock = threading.Lock()


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    """A limit that will not clear during this run (e.g. a per-day cap)."""


class PayloadTooLarge(LLMError):
    """The request exceeds the model's per-request or per-minute input budget."""


def gate(provider, model):
    """One in-flight request per model, so workers queue instead of colliding."""
    key = f"{provider}:{model}"
    with _gates_lock:
        if key not in _gates:
            _gates[key] = threading.Lock()
        return _gates[key]


_RETRY_AFTER = re.compile(r"try again in ([\d.]+)\s*s", re.I)


def retry_delay(resp, attempt):
    """Seconds to wait, preferring the provider's own instruction."""
    m = _RETRY_AFTER.search(resp.text or "")
    if m:
        return min(MAX_SLEEP, float(m.group(1)) + 1.0)
    h = resp.headers.get("retry-after")
    if h:
        try:
            return min(MAX_SLEEP, float(h) + 1.0)
        except ValueError:
            pass
    return min(30.0, 4.0 * attempt)


def is_daily_cap(text):
    t = (text or "").lower()
    return "per-day" in t or "free-models-per-day" in t or "per day" in t


def chat(provider, model, system, user, temperature=0.2, max_tokens=16000, retries=6,
         reasoning_effort="low"):
    """Returns (text, meta). Raises LLMError after the attempts are used up.

    Several study models are reasoning models that bill chain-of-thought against
    the completion budget. Left unconstrained they exhaust `max_tokens` on
    deliberation and return a truncated answer or none at all, so reasoning is
    held to the lowest setting each provider exposes.
    """
    cfg = PROVIDERS[provider]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if reasoning_effort:
        if provider == "groq":
            payload["reasoning_effort"] = reasoning_effort
        elif provider == "openrouter":
            payload["reasoning"] = {"effort": reasoning_effort, "exclude": True}
    keys = cfg.get("keys") or [cfg["key"]]
    ki = 0
    headers = {"Authorization": f"Bearer {keys[ki]}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Jamaludiin/Automated-TestCase-RAG"
        headers["X-Title"] = "RAGTestGen"

    last = None
    exhausted = set()          # keys whose daily cap is spent
    lock = gate(provider, model)
    # one extra attempt per spare key, so a run does not end when one key's
    # free-tier quota does
    attempts = retries + len(keys) - 1
    for attempt in range(1, attempts + 1):
        t0 = time.time()
        try:
            with lock:
                resp = requests.post(cfg["base_url"] + "/chat/completions",
                                     json=payload, headers=headers, timeout=TIMEOUT)
            if resp.status_code != 200:
                last = f"HTTP {resp.status_code}: {resp.text[:300]}"
                # Not every model accepts the graded effort levels; those that
                # reject them are retried with reasoning simply turned off.
                if resp.status_code == 400 and "reasoning_effort" in resp.text \
                        and payload.get("reasoning_effort") not in (None, "none"):
                    payload["reasoning_effort"] = "none"
                    continue
                # Too large for this model's budget: waiting will not help, but
                # a smaller batch will, so tell the caller which failure it was.
                if resp.status_code == 413 or (
                        resp.status_code == 429 and "too large" in resp.text.lower()):
                    raise PayloadTooLarge(last)
                if resp.status_code in (401, 402, 403, 429):
                    if resp.status_code == 429 and is_daily_cap(resp.text):
                        exhausted.add(ki)
                    if ki + 1 < len(keys) and (resp.status_code != 429
                                               or ki in exhausted):
                        ki += 1
                        headers["Authorization"] = f"Bearer {keys[ki]}"
                        continue
                    if len(exhausted) == len(keys):
                        raise QuotaExhausted(last)
                if resp.status_code not in (408, 409, 429, 500, 502, 503, 504):
                    break
                time.sleep(retry_delay(resp, attempt))
                continue
            d = resp.json()
            if "choices" not in d:
                last = f"no choices: {json.dumps(d)[:300]}"
                time.sleep(3 * attempt)
                continue
            choice = d["choices"][0]
            text = choice["message"].get("content") or ""
            usage = d.get("usage", {})
            meta = {"latency_s": round(time.time() - t0, 2),
                    "finish_reason": choice.get("finish_reason"),
                    "usage": usage, "attempts": attempt,
                    "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                        "reasoning_tokens")}
            if not text.strip():
                last = (f"empty content (finish={choice.get('finish_reason')}, "
                        f"reasoning_tokens={meta['reasoning_tokens']})")
                time.sleep(2 * attempt)
                continue
            return text, meta
        except (PayloadTooLarge, QuotaExhausted):
            raise
        except Exception as e:
            # Includes transient loss of connectivity, which can outlast a short
            # backoff, so this one grows faster than the in-protocol retries.
            last = f"{type(e).__name__}: {e}"
            time.sleep(min(120, 8 * attempt * attempt))
    raise LLMError(last or "unknown error")
