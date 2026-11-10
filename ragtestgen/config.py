"""Configuration for RAGTestGen experiments.

API keys are read from the environment; .env is a fallback for local runs and
must never be committed.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

def _keys(prefix):
    """All keys for a provider: PREFIX, then PREFIX_2, PREFIX_3, ... in order.

    Free-tier accounts have low daily limits, so a run can outlast a single key;
    the client falls through to the next one when a key is rate-limited.
    """
    names = [prefix] + sorted(k for k in os.environ
                              if k.startswith(prefix + "_") and k != prefix)
    return [v for v in (os.environ.get(n, "").strip() for n in names) if v]


GROQ_API_KEYS = _keys("GROQ_API_KEY")
OPENROUTER_API_KEYS = _keys("OPENROUTER_API_KEY")
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
OPENROUTER_API_KEY = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else ""

PROVIDERS = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key": GROQ_API_KEY,
             "keys": GROQ_API_KEYS},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key": OPENROUTER_API_KEY,
                   "keys": OPENROUTER_API_KEYS},
}

# Model registry. `short` is the label used in tables and charts.
MODELS = {}


def register(short, provider, model_id, family, params_b=None, hosted="cloud",
             reasoning_effort="low", max_tokens=16000, batch=None):
    """`max_tokens` and `batch` exist to fit free-tier per-minute budgets.

    Groq enforces an output-tokens-per-minute cap per model and rejects any
    request whose `max_tokens` alone exceeds it, so a model with a small cap has
    to ask for fewer methods per request rather than a smaller answer per method.
    """
    MODELS[short] = {"short": short, "provider": provider, "model": model_id,
                     "family": family, "params_b": params_b, "hosted": hosted,
                     "reasoning_effort": reasoning_effort,
                     "max_tokens": max_tokens, "batch": batch}


# Populated by scripts/select_models.py after availability screening.
# Study models, chosen after availability screening (scripts/screen_models.py).
# Selected for diversity of provider, vendor family and parameter scale so that
# cross-model agreement is not an artefact of a single lineage.
register("gptoss120b",  "groq",       "openai/gpt-oss-120b",             "GPT-OSS",   120)
register("gptoss20b",   "groq",       "openai/gpt-oss-20b",              "GPT-OSS",    20)
# qwen3.6 rejects the graded effort levels (Groq exposes only none/default here)
# and is capped at 1000 output tokens/min, so it asks for one method at a time.
register("qwen3_6_27b", "groq",       "qwen/qwen3.6-27b",                "Qwen3",      27,
         reasoning_effort="none", max_tokens=1000, batch=1)
register("laguna_s",    "openrouter", "poolside/laguna-s-2.1:free",      "Laguna",   None)
register("nemotron120", "openrouter", "nvidia/nemotron-3-super-120b-a12b:free", "Nemotron", 120)

# The two OpenRouter models are registered but excluded from the study: their
# free tier allows 50 requests/day against the ~240 a single condition needs, a
# cap no amount of in-run pacing clears. Re-add them if the account is funded.
STUDY_MODELS = ["gptoss120b", "gptoss20b", "qwen3_6_27b"]
