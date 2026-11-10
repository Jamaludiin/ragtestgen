#!/usr/bin/env python3
"""Phase 2: screen candidate models on a realistic generation task.

A model enters the study only if it can (a) respond, and (b) honour the
required output format well enough to yield parseable JUnit tests.
"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ragtestgen import prompts
from ragtestgen.llm import chat, LLMError

CANDIDATES = [
    ("gptoss120b",  "groq",       "openai/gpt-oss-120b"),
    ("gptoss20b",   "groq",       "openai/gpt-oss-20b"),
    ("qwen3_8_27b", "groq",       "qwen/qwen3.8-27b"),
    ("qwen3_6_27b", "groq",       "qwen/qwen3.6-27b"),
    ("laguna_s",    "openrouter", "poolside/laguna-s-2.1:free"),
    ("laguna_xs",   "openrouter", "poolside/laguna-xs-2.1:free"),
    ("north_code",  "openrouter", "cohere/north-mini-code:free"),
    ("nemotron120", "openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("nemotron550", "openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ("gemma4_31b",  "openrouter", "google/gemma-4-31b-it:free"),
    ("inkling",     "openrouter", "thinkingmachines/inkling:free"),
    ("nex_pro",     "openrouter", "nex-agi/nex-n2.5-pro:free"),
    ("ling_flash",  "openrouter", "inclusionai/ling-3.0-flash-fin:free"),
    ("dots3",       "openrouter", "dots-studio/dots-3-note-preview:free"),
]

SRC = """\
public class Stack {
    private int[] a; private int n;
    public Stack(int cap) { if (cap <= 0) throw new IllegalArgumentException("cap"); a = new int[cap]; }
    public void push(int v) { if (n == a.length) throw new IllegalStateException("full"); a[n++] = v; }
    public int pop() { if (n == 0) throw new IllegalStateException("empty"); return a[--n]; }
    public boolean isEmpty() { return n == 0; }
}"""

TARGETS = [
    {"class": "Stack", "name": "push", "params": ["int"], "visibility": "public",
     "complexity": 2, "constructor": False, "static": False},
    {"class": "Stack", "name": "pop", "params": [], "visibility": "public",
     "complexity": 2, "constructor": False, "static": False},
]


def probe(entry):
    short, provider, model = entry
    user = prompts.build("(none retrieved)", SRC, TARGETS, "", per_method=2)
    t0 = time.time()
    try:
        raw, meta = chat(provider, model, prompts.SYSTEM, user, max_tokens=4000, retries=2)
    except LLMError as e:
        return {"short": short, "provider": provider, "model": model,
                "ok": False, "error": str(e)[:200], "tests": 0}
    tests, st = prompts.parse(raw)
    return {"short": short, "provider": provider, "model": model, "ok": len(tests) > 0,
            "tests": len(tests), "format_compliant": st["format_compliant"],
            "used_fallback": st["used_fallback"], "latency_s": round(time.time() - t0, 1),
            "finish": meta.get("finish_reason"),
            "completion_tokens": meta.get("usage", {}).get("completion_tokens"),
            "error": None}


def main():
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(probe, CANDIDATES))
    res.sort(key=lambda r: (not r["ok"], -r["tests"]))
    print(f"{'short':13s} {'provider':11s} {'ok':3s} {'tests':>5s} {'fmt':4s} {'lat':>6s}  note")
    for r in res:
        print(f"{r['short']:13s} {r['provider']:11s} {str(r['ok']):3s} {r['tests']:5d} "
              f"{str(r.get('format_compliant','-'))[:4]:4s} {str(r.get('latency_s','-')):>6s}  "
              f"{(r.get('error') or r.get('finish') or '')[:70]}")
    Path("screen_report.json").write_text(json.dumps(res, indent=1))
    print("\nPASSED:", [r["short"] for r in res if r["ok"]])


if __name__ == "__main__":
    main()
