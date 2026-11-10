#!/usr/bin/env python3
"""Phase 1: curate the benchmark.

For every program directory, separate production sources from pre-existing test
files (Randoop regression suites and hand-written JUnit tests), then try to
compile the production sources with javac. Programs that do not compile are
excluded from the study and the reason is recorded.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

import argparse
_ap = argparse.ArgumentParser(description="Curate benchmark programs into bench/<program>/{src,randoop,classes}.")
_ap.add_argument("--source", required=True, help="directory with one sub-directory per candidate Java program")
_ap.add_argument("--dest", default=str(Path(__file__).resolve().parent.parent / "bench"), help="output directory (default: <repo>/bench)")
_args = _ap.parse_args()
ROOT = Path(_args.source).expanduser().resolve()
WORK = Path(_args.dest).expanduser().resolve()

TEST_PAT = re.compile(r"(RegressionTest|ErrorTest|.*Test\d*|.*Tests)\.java$", re.I)
RANDOOP_PAT = re.compile(r"(RegressionTest|ErrorTest)\d*\.java$")

# Dropped from the benchmark by choice, not by a property of the code. Listed
# here rather than deleted from ProgramsUnderTest so the decision is visible and
# reversible; re-running this script keeps them out.
DROPPED = {"QuizProject", "QuizProject2", "MustafeProject", "JUnit5"}


def classify(files):
    prod, randoop, other_tests = [], [], []
    for f in files:
        name = f.name
        body = f.read_text(errors="replace")
        is_test = ("org.junit" in body or "org.testng" in body
                   or "junit.framework" in body or "@Test" in body)
        if RANDOOP_PAT.match(name):
            randoop.append(f)
        elif is_test or TEST_PAT.match(name):
            other_tests.append(f)
        else:
            prod.append(f)
    return prod, randoop, other_tests


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    report = {}
    EXTERNAL_DEPS = {"DoubleLinkedLists": "requires edu.ksu.cis SpExJava specification library",
                     "alocationVector": "requires gov.nasa.jpf (Java PathFinder) runtime"}
    for prog in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        if prog.name in DROPPED:
            report[prog.name] = {"status": "excluded", "reason": "dropped from the study"}
            continue
        files = sorted(prog.rglob("*.java"))
        if not files:
            report[prog.name] = {"status": "excluded", "reason": "no .java files"}
            continue
        prod, randoop, other = classify(files)
        if not prod:
            report[prog.name] = {"status": "excluded", "reason": "only test files present"}
            continue

        dest = WORK / prog.name
        src = dest / "src"
        src.mkdir(parents=True)
        # preserve package directory structure relative to the nearest 'src' dir
        for f in prod:
            parts = f.parts
            rel = Path(*parts[parts.index("src") + 1:]) if "src" in parts else Path(f.name)
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, src / rel)
        rd = dest / "randoop"
        if randoop:
            rd.mkdir()
            for f in randoop:
                shutil.copy2(f, rd / f.name)

        classes = dest / "classes"
        classes.mkdir()
        java_files = [str(p) for p in src.rglob("*.java")]
        r = subprocess.run(["javac", "-nowarn", "-d", str(classes), *java_files],
                           capture_output=True, text=True)
        n_class = len(list(classes.rglob("*.class")))
        report[prog.name] = {
            "status": "ok" if r.returncode == 0 and n_class else "excluded",
            "reason": "" if r.returncode == 0 and n_class else EXTERNAL_DEPS.get(
                prog.name, (r.stderr.strip().splitlines() or ["no classes"])[0][:200]),
            "prod_files": len(prod), "randoop_files": len(randoop),
            "other_test_files": len(other), "classes_compiled": n_class,
            "loc": sum(len(p.read_text(errors="replace").splitlines()) for p in src.rglob("*.java")),
        }
    Path("bench_report.json").write_text(json.dumps(report, indent=1))
    ok = [k for k, v in report.items() if v["status"] == "ok"]
    print(f"{'program':22s} {'status':9s} {'prod':>4s} {'cls':>4s} {'LOC':>5s} {'randoop':>7s}  reason")
    for k, v in report.items():
        print(f"{k:22s} {v['status']:9s} {v.get('prod_files',0):4d} {v.get('classes_compiled',0):4d} "
              f"{v.get('loc',0):5d} {v.get('randoop_files',0):7d}  {v.get('reason','')[:70]}")
    print(f"\nCOMPILING: {len(ok)}/{len(report)} -> {ok}")


if __name__ == "__main__":
    main()
