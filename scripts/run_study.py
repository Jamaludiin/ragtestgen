#!/usr/bin/env python3
"""Phase 3: run the study.

Two stages, each cached to disk so the study can be resumed after an
interruption without repeating paid or slow work:

  generate  (network-bound)  -> runs/<condition>/<prog>__<model>/gen.json
  evaluate  (CPU-bound)      -> runs/<condition>/<prog>__<model>/eval.json

Conditions
  full     every testable method up to MAX_TARGETS, ordered by complexity.
           This is the tool as it is meant to be used.
  prio50 / naive50
           half the methods (rounded up, minimum three). `prio50` spends that
           budget on the most complex methods, `naive50` on the first ones in
           declaration order. The pair isolates what prioritisation buys,
           holding model, prompt, retrieval and budget fixed.
"""
import argparse, json, math, os, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ragtestgen import pipeline as P
from ragtestgen.config import MODELS, STUDY_MODELS

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def budget(n_methods, condition):
    if condition == "full":
        return min(n_methods, P.MAX_TARGETS)
    return max(3, math.ceil(n_methods / 2))


def targets_for(prog, condition):
    m = prog["methods"]
    k = budget(len(m), condition)
    if condition == "naive50":
        # declaration order: file, then position in file
        ordered = sorted(m, key=lambda x: (x["file"], x["startLine"]))[:k]
    else:
        ordered = sorted(m, key=lambda x: (-x["complexity"], x["class"], x["name"]))[:k]
    return sorted(ordered, key=lambda x: (x["class"], x["startLine"]))


def workdir(condition, prog, model):
    return RUNS / condition / f"{prog}__{model}"


def programs_ok():
    rep = json.loads((ROOT / "bench_report.json").read_text())
    return [k for k, v in rep.items() if v["status"] == "ok"]


# ---------------------------------------------------------------- generation
def gen_one(args):
    condition, prog_name, model_key = args
    d = workdir(condition, prog_name, model_key)
    out = d / "gen.json"
    if out.exists():
        n = json.loads(out.read_text())["parse"]["tests_parsed"]
        # A cached run that produced nothing is usually a transient provider
        # limit rather than a model result, so it is retried; only a suite with
        # tests is treated as settled work not worth paying for twice.
        if n:
            return (prog_name, model_key, "cached", n)
        (d / "eval.json").unlink(missing_ok=True)
    try:
        prog = PROG_CACHE[prog_name]
        tg = targets_for(prog, condition)
        gen = P.generate(prog, MODELS[model_key], tg)
        gen["targets"] = [{"class": m["class"], "name": m["name"], "complexity": m["complexity"],
                           "params": m["params"], "startLine": m["startLine"],
                           "visibility": m["visibility"], "static": m["static"],
                           "constructor": m["constructor"]} for m in tg]
        gen["condition"], gen["program"], gen["model"] = condition, prog_name, model_key
        d.mkdir(parents=True, exist_ok=True)
        (d / "raw.txt").write_text(gen.pop("raw", ""))
        out.write_text(json.dumps(gen, indent=1))
        return (prog_name, model_key, "ok" if gen["ok"] else "empty", gen["parse"]["tests_parsed"])
    except Exception as e:
        traceback.print_exc()
        return (prog_name, model_key, f"ERR {type(e).__name__}: {e}", 0)


PROG_CACHE = {}


def stage_generate(condition, progs, models, workers):
    global PROG_CACHE
    # index building is CPU-heavy; do it once per program in the parent
    for p in progs:
        if p not in PROG_CACHE:
            PROG_CACHE[p] = P.load_program(p)
    jobs = [(condition, p, m) for p in progs for m in models]
    print(f"[generate/{condition}] {len(jobs)} runs, {workers} workers", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(gen_one, j): j for j in jobs}
        for f in as_completed(futs):
            prog, model, status, n = f.result()
            done += 1
            print(f"  [{done}/{len(jobs)}] {prog:22s} {model:12s} {status:10s} tests={n}", flush=True)


# ---------------------------------------------------------------- evaluation
def eval_one(args):
    condition, prog_name, model_key = args
    d = workdir(condition, prog_name, model_key)
    out = d / "eval.json"
    if out.exists():
        r = json.loads(out.read_text())
        return (prog_name, model_key, "cached", r["kept"], r["line_pct"])
    gf = d / "gen.json"
    if not gf.exists():
        return (prog_name, model_key, "nogen", 0, 0.0)
    try:
        import sys as _s
        _s.path.insert(0, str(ROOT))
        from ragtestgen import pipeline as _P
        gen = json.loads(gf.read_text())
        prog = _P.load_program(prog_name)
        t0 = time.time()
        ev = _P.evaluate(prog, model_key, gen, d)
        ev["line_pct"] = _P.pct(ev["suite"], "line")
        ev["branch_pct"] = _P.pct(ev["suite"], "branch")
        ev["instr_pct"] = _P.pct(ev["suite"], "instr")
        ev["eval_s"] = round(time.time() - t0, 1)
        ev["condition"], ev["program"], ev["model"] = condition, prog_name, model_key
        out.write_text(json.dumps(ev, indent=1))
        return (prog_name, model_key, "ok", ev["kept"], ev["line_pct"])
    except Exception as e:
        return (prog_name, model_key, f"ERR {type(e).__name__}: {str(e)[:120]}", 0, 0.0)


def stage_evaluate(condition, progs, models, workers):
    jobs = [(condition, p, m) for p in progs for m in models]
    print(f"[evaluate/{condition}] {len(jobs)} runs, {workers} workers", flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(eval_one, j): j for j in jobs}
        for f in as_completed(futs):
            prog, model, status, kept, line = f.result()
            done += 1
            print(f"  [{done}/{len(jobs)}] {prog:22s} {model:12s} {status:34s} "
                  f"kept={kept:3d} line={line:5.1f}%", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", default="full", choices=["full", "prio50", "naive50"])
    ap.add_argument("--stage", default="both", choices=["generate", "evaluate", "both"])
    ap.add_argument("--programs", nargs="*", default=None)
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--gen-workers", type=int, default=6)
    ap.add_argument("--eval-workers", type=int, default=4)
    a = ap.parse_args()
    progs = a.programs or programs_ok()
    models = a.models or STUDY_MODELS
    if a.stage in ("generate", "both"):
        stage_generate(a.condition, progs, models, a.gen_workers)
    if a.stage in ("evaluate", "both"):
        stage_evaluate(a.condition, progs, models, a.eval_workers)


if __name__ == "__main__":
    main()
