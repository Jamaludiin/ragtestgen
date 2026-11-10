#!/usr/bin/env python3
"""Phase 4: collect the study into an analysable, traceable dataset.

Reads every runs/<condition>/<program>__<model>/{gen,eval}.json and writes a
self-contained `results/` directory:

  data/runs.csv        one row per run (the analysis unit)
  data/tests.csv       one row per generated test case
  data/programs.csv    the benchmark subjects
  data/manifest.json   provenance: config, checksums, timestamps, gaps

Nothing here recomputes a measurement. Every column is either copied from a run
artefact or derived from copied columns by an arithmetic that is stated in
`manifest.json`, so any number in the paper can be traced to the run directory
it came from and, from there, to raw.txt and suite.exec.
"""
import csv, hashlib, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ragtestgen.config import MODELS, STUDY_MODELS

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
OUT = ROOT / "results"
CONDITIONS = ["full", "prio50", "naive50"]


def sha(path, n=1 << 16):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(n):
            h.update(chunk)
    return h.hexdigest()[:16]


def pct(cov, key):
    c, m = cov.get(f"{key}_covered", 0), cov.get(f"{key}_missed", 0)
    return round(100 * c / (c + m), 2) if (c + m) else None


def collect():
    """One record per run, plus the per-test records underneath it."""
    runs, tests, gaps = [], [], []
    for cond in CONDITIONS:
        cdir = RUNS / cond
        if not cdir.exists():
            continue
        for d in sorted(cdir.iterdir()):
            gf, ef = d / "gen.json", d / "eval.json"
            if not gf.exists():
                continue
            G = json.loads(gf.read_text())
            if G["model"] not in STUDY_MODELS:
                continue          # models registered but excluded from the study
            E = json.loads(ef.read_text()) if ef.exists() else {}
            res = E.get("results", [])
            n_gen = G["parse"]["tests_parsed"]
            n_kept = E.get("kept")
            n_pass = sum(1 for r in res if r["status"] == "pass") or None if res else None
            batches = G.get("batches", [])
            ok_b = [b for b in batches if b.get("ok")]
            # a run that produced nothing is a provider failure, not a result;
            # it is kept in the dataset and flagged rather than dropped
            err = "" if n_gen else "; ".join(
                (b.get("error") or "")[:120] for b in batches if not b.get("ok"))[:300]
            rec = {
                "condition": cond, "program": G["program"], "model": G["model"],
                "family": MODELS[G["model"]]["family"],
                "params_b": MODELS[G["model"]]["params_b"],
                # --- targeting
                "n_targets": len(G.get("targets", [])),
                "mean_complexity": round(
                    sum(t["complexity"] for t in G["targets"]) / len(G["targets"]), 3)
                    if G.get("targets") else None,
                "max_complexity": max((t["complexity"] for t in G["targets"]), default=None),
                # --- stage 1: format adherence
                "tests_expected": G["parse"]["expected_tests"],
                "tests_generated": n_gen,
                "yield": G["parse"]["yield"],
                "format_compliant": G["parse"]["format_compliant"],
                "used_fallback": any(b.get("used_fallback") for b in ok_b),
                "batches_ok": G["parse"]["batches_ok"],
                "batches_total": G["parse"]["batches_total"],
                # --- stage 2: compilation validity
                "tests_compiled": n_kept,
                "tests_dropped": len(E["dropped"]) if "dropped" in E else None,
                "compile_rate": round(n_kept / n_gen, 4) if n_kept is not None and n_gen else None,
                # --- stage 3: execution
                "tests_passed": n_pass,
                "pass_rate": round(n_pass / n_kept, 4) if n_pass and n_kept else None,
                # --- stage 4: adequacy
                "line_pct": E.get("line_pct"), "branch_pct": E.get("branch_pct"),
                "instr_pct": E.get("instr_pct"),
                "line_covered": E.get("suite", {}).get("line_covered"),
                "line_total": (E.get("suite", {}).get("line_covered", 0)
                               + E.get("suite", {}).get("line_missed", 0)) or None,
                "branch_covered": E.get("suite", {}).get("branch_covered"),
                "branch_total": (E.get("suite", {}).get("branch_covered", 0)
                                 + E.get("suite", {}).get("branch_missed", 0)) or None,
                # --- cost
                "completion_tokens": G["llm_meta"]["completion_tokens"],
                "reasoning_tokens": G["llm_meta"]["reasoning_tokens"],
                "llm_latency_s": G["llm_meta"]["total_latency_s"],
                "gen_wall_s": G["wall_s"], "eval_s": E.get("eval_s"),
                # --- retrieval / prompt covariates
                "index_chunks": max((b.get("index_chunks", 0) for b in batches), default=None),
                "mean_prompt_chars": round(
                    sum(b.get("prompt_chars", 0) for b in batches) / len(batches))
                    if batches else None,
                "context_dropped": any(b.get("context_dropped") for b in batches),
                "bodies_elided": any(b.get("bodies_elided") for b in batches),
                # --- integrity
                "status": "ok" if n_gen and n_kept else ("no_tests" if not n_gen else "no_compile"),
                "error": err,
                "run_dir": str(d.relative_to(ROOT)),
                "gen_sha256": sha(gf), "eval_sha256": sha(ef) if ef.exists() else "",
            }
            runs.append(rec)
            if not n_gen:
                gaps.append({"condition": cond, "program": G["program"],
                             "model": G["model"], "error": err})

            by_id = {r["id"]: r for r in res if "id" in r}
            for t in G.get("tests", []):
                r = by_id.get(t.get("id"), {})
                tests.append({
                    "condition": cond, "program": G["program"], "model": G["model"],
                    "test_id": t.get("id"), "test_name": t.get("test_name"),
                    "target_method": t.get("method"), "category": t.get("category"),
                    "parsed_by": t.get("parsed_by"),
                    "status": r.get("status", "not_compiled"),
                    "line_covered": r.get("line_covered"),
                    "branch_covered": r.get("branch_covered"),
                    "instr_covered": r.get("instr_covered"),
                    "run_dir": str(d.relative_to(ROOT)),
                })
    return runs, tests, gaps


def programs():
    rep = json.loads((ROOT / "bench_report.json").read_text())
    return [{"program": k, **{c: v.get(c) for c in
                              ("prod_files", "randoop_files", "other_test_files",
                               "classes_compiled", "loc")}}
            for k, v in sorted(rep.items()) if v.get("status") == "ok"]


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.relative_to(ROOT)}  ({len(rows)} rows)")


def main():
    runs, tests, gaps = collect()
    progs = programs()
    data = OUT / "data"
    print("writing dataset:")
    write_csv(data / "runs.csv", runs)
    write_csv(data / "tests.csv", tests)
    write_csv(data / "programs.csv", progs)

    java = subprocess.run(["java", "-version"], capture_output=True, text=True)
    manifest = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "study": {
            "conditions": CONDITIONS,
            "models": {m: MODELS[m] for m in STUDY_MODELS},
            "programs": [p["program"] for p in progs],
            "design": "3 conditions x 3 models x %d programs" % len(progs),
            "expected_runs": len(CONDITIONS) * len(STUDY_MODELS) * len(progs),
            "collected_runs": len(runs),
        },
        "controls": {
            "temperature": 0.2, "tests_per_method": 4, "max_targets": 15,
            "batch_methods_per_request": 4,
            "retrieval": {"chunk_chars": 500, "stride": 400, "n_results": 10,
                          "embedding": "all-MiniLM-L6-v2 (ChromaDB ONNX)"},
            "prompt_budget_chars": 20000,
        },
        "derived_columns": {
            "compile_rate": "tests_compiled / tests_generated",
            "pass_rate": "tests_passed / tests_compiled",
            "yield": "tests_generated / tests_expected",
            "line_pct": "100 * line_covered / (line_covered + line_missed), from JaCoCo suite.exec",
            "branch_pct": "100 * branch_covered / (branch_covered + branch_missed)",
        },
        "integrity": {
            "runs_with_tests": sum(1 for r in runs if r["tests_generated"]),
            "runs_without_tests": len(gaps),
            "gaps": gaps,
            "note": "Runs without tests are provider failures (rate limits / network), "
                    "not model results. They are retained in runs.csv with status "
                    "'no_tests' and an error string, and MUST be excluded from "
                    "generation-quality means and reported separately.",
        },
        "environment": {
            "python": sys.version.split()[0],
            "java": (java.stderr or java.stdout).splitlines()[0] if (java.stderr or java.stdout) else "",
        },
    }
    (OUT / "data" / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"  results/data/manifest.json")
    print(f"\ncollected {len(runs)} runs, {len(tests)} tests, {len(progs)} programs")
    if gaps:
        print(f"WARNING: {len(gaps)} runs have no tests (provider failures):")
        for g in gaps:
            print(f"  {g['condition']:8s} {g['program']:20s} {g['model']}")


if __name__ == "__main__":
    main()
