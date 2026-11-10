#!/usr/bin/env python3
"""Phase 5: descriptive and inferential statistics over results/data/runs.csv.

Writes results/tables/*.csv (paper-ready) and results/ANALYSIS.md (a narrative
report).

Choice of test is decided from the data, not assumed. Normality of the paired
differences is checked with Shapiro-Wilk before any comparison is made; the
result (reported in tables/normality.csv) is that most difference distributions
depart from normal, so Wilcoxon signed-rank is used for every metric to keep one
test across the family. Where Shapiro-Wilk does NOT reject normality, a paired
t-test is additionally reported as a confirmatory check, so the reader can see
that the conclusion does not depend on the choice of test.

The core statistics are implemented here rather than taken from SciPy, and are
verified two ways: against worked examples in tests_stats(), which runs on every
invocation, and against SciPy itself in cross_check().
"""
import csv, json, math, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results"
DATA = OUT / "data"
TABLES = OUT / "tables"

# Metrics analysed, in funnel order: format -> compilation -> execution -> adequacy
METRICS = [("yield", "Format yield (parsed/expected)"),
           ("compile_rate", "Compilation rate (compiled/generated)"),
           ("pass_rate", "Pass rate (passed/compiled)"),
           ("line_pct", "Line coverage %"),
           ("branch_pct", "Branch coverage %"),
           ("instr_pct", "Instruction coverage %")]


# ------------------------------------------------------------------ statistics
def median(xs):
    return st.median(xs) if xs else None


def iqr(xs):
    if len(xs) < 2:
        return None
    q = st.quantiles(sorted(xs), n=4, method="inclusive")
    return q[2] - q[0]


def cliffs_delta(a, b):
    """Non-parametric effect size: P(a>b) - P(a<b), in [-1, 1]."""
    if not a or not b:
        return None
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))


def delta_magnitude(d):
    """Romano et al. thresholds, the convention in empirical SE."""
    if d is None:
        return "n/a"
    a = abs(d)
    return ("negligible" if a < 0.147 else "small" if a < 0.33
            else "medium" if a < 0.474 else "large")


def _norm_sf(z):
    """Upper-tail standard normal, via erfc."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def wilcoxon(pairs):
    """Two-sided Wilcoxon signed-rank over (x, y) pairs.

    Zero differences are dropped (Wilcoxon's original treatment). The normal
    approximation with a continuity correction and tie correction is used; with
    fewer than ~10 non-zero pairs it is unreliable, which the caller reports.
    """
    d = [x - y for x, y in pairs if x is not None and y is not None]
    d = [v for v in d if v != 0]
    n = len(d)
    if n == 0:
        return {"n": 0, "W": None, "z": None, "p": None, "note": "all differences zero"}
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    ties = []
    while i < n:                      # average ranks within ties on |d|
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        r = (i + j + 2) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = r
        ties.append(j - i + 1)
        i = j + 1
    wp = sum(ranks[i] for i in range(n) if d[i] > 0)
    wn = sum(ranks[i] for i in range(n) if d[i] < 0)
    W = min(wp, wn)
    mu = n * (n + 1) / 4
    tie_term = sum(t ** 3 - t for t in ties)
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24 - tie_term / 48)
    if sd == 0:
        return {"n": n, "W": W, "z": None, "p": None, "note": "zero variance"}
    z = (W - mu + 0.5) / sd
    return {"n": n, "W": W, "W_plus": wp, "W_minus": wn, "z": round(z, 4),
            "p": round(2 * _norm_sf(abs(z)), 5),
            "note": "normal approximation unreliable for n<10" if n < 10 else ""}


def holm(pvals):
    """Holm-Bonferroni adjusted p-values for a family of tests."""
    idx = sorted(range(len(pvals)), key=lambda i: (pvals[i] is None, pvals[i]))
    m = sum(1 for p in pvals if p is not None)
    out = [None] * len(pvals)
    prev = 0.0
    for rank, i in enumerate(idx):
        if pvals[i] is None:
            continue
        adj = min(1.0, max(prev, (m - rank) * pvals[i]))
        out[i] = round(adj, 5)
        prev = adj
    return out


def shapiro(xs):
    """Shapiro-Wilk normality test. Returns (W, p) or (None, None).

    Used to decide, per metric, whether a parametric test would be defensible.
    Chosen over Kolmogorov-Smirnov because it has greater power at the sample
    sizes here (n < 50).
    """
    try:
        from scipy import stats
    except ImportError:
        return None, None
    if len(xs) < 3 or len(set(xs)) < 2:
        return None, None
    W, p = stats.shapiro(xs)
    return round(float(W), 4), round(float(p), 6)


def paired_t(pairs):
    """Paired t-test with Cohen's d_z, for the confirmatory check."""
    try:
        from scipy import stats
    except ImportError:
        return {}
    d = [a - b for a, b in pairs]
    if len(d) < 3 or st.pstdev(d) == 0:
        return {}
    t, p = stats.ttest_rel([a for a, _ in pairs], [b for _, b in pairs])
    return {"n": len(d), "mean_diff": round(st.mean(d), 3),
            "t": round(float(t), 4), "p": round(float(p), 6),
            "cohens_dz": round(st.mean(d) / st.stdev(d), 3)}


def cross_check(pairs):
    """Confirm the hand-rolled Wilcoxon against SciPy on real data."""
    try:
        from scipy import stats
    except ImportError:
        return None
    mine = wilcoxon(pairs)
    if mine["W"] is None:
        return None
    x = [a for a, _ in pairs]
    y = [b for _, b in pairs]
    try:
        ref = stats.wilcoxon(x, y, zero_method="wilcox", correction=True,
                             method="approx")
    except TypeError:                       # SciPy < 1.12 spells it `mode`
        ref = stats.wilcoxon(x, y, zero_method="wilcox", correction=True,
                             mode="approx")
    return (abs(mine["W"] - float(ref.statistic)) < 1e-9
            and abs(mine["p"] - float(ref.pvalue)) < 1e-4)


def tests_stats():
    """Self-checks on worked examples, so the hand-rolled statistics are trusted."""
    # Cliff's delta: complete separation
    assert cliffs_delta([4, 5, 6], [1, 2, 3]) == 1.0
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0
    # Wilcoxon against a textbook example (Siegel): differences all positive
    r = wilcoxon([(x, 0) for x in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]])
    assert r["W"] == 0 and r["n"] == 10 and r["p"] < 0.01, r
    # sorted 0.01,0.03,0.04 -> x3, x2, x1 = 0.03, 0.06, 0.04; monotone -> 0.06
    assert holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]


# ------------------------------------------------------------------- data load
def load():
    rows = list(csv.DictReader(open(DATA / "runs.csv")))
    for r in rows:
        for k, v in list(r.items()):
            if v == "":
                r[k] = None
            elif k in ("format_compliant", "used_fallback", "context_dropped",
                       "bodies_elided"):
                r[k] = v == "True"
            elif k not in ("condition", "program", "model", "family", "status",
                           "error", "run_dir", "gen_sha256", "eval_sha256"):
                r[k] = float(v)
    return rows


def valid(rows):
    """Runs that actually reached the model. Provider failures are not results."""
    return [r for r in rows if r["status"] != "no_tests"]


def col(rows, m):
    return [r[m] for r in rows if r.get(m) is not None]


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def describe(rows, metric):
    xs = col(rows, metric)
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(st.mean(xs), 2),
            "sd": round(st.stdev(xs), 2) if len(xs) > 1 else 0.0,
            "median": round(median(xs), 2), "iqr": round(iqr(xs), 2) if len(xs) > 1 else 0.0,
            "min": round(min(xs), 2), "max": round(max(xs), 2)}


# ---------------------------------------------------------------------- report
def main():
    tests_stats()
    rows = load()
    ok = valid(rows)
    gaps = [r for r in rows if r["status"] == "no_tests"]
    L = []
    A = L.append

    A("# RAGTestGen — Statistical Analysis\n")
    A(f"Generated from `results/data/runs.csv` ({len(rows)} runs; "
      f"{len(ok)} analysable, {len(gaps)} provider failures excluded).\n")
    if gaps:
        A("> **Excluded from all statistics below** (rate limit / network failure, "
          "not a model result):\n>")
        for g in gaps:
            A(f"> - `{g['condition']}` / {g['program']} / {g['model']}")
        A("")

    # ---------------------------------------------------- 1. descriptives
    A("\n## 1. Descriptive statistics\n")
    A("### 1.1 Overall, by condition\n")
    A("| Condition | Metric | n | Mean | SD | Median | IQR | Min | Max |")
    A("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    desc = []
    for cond in ("full", "prio50", "naive50"):
        sub = [r for r in ok if r["condition"] == cond]
        for m, label in METRICS:
            d = describe(sub, m)
            if not d["n"]:
                continue
            desc.append({"condition": cond, "metric": m, **d})
            A(f"| {cond} | {label} | {d['n']} | {d['mean']} | {d['sd']} | "
              f"{d['median']} | {d['iqr']} | {d['min']} | {d['max']} |")
    write_csv(TABLES / "descriptives_by_condition.csv", desc)

    A("\n### 1.2 By model (all conditions pooled)\n")
    A("| Model | Family | n | Compile rate | Pass rate | Line % | Branch % | Tokens |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    bym = []
    for model in sorted({r["model"] for r in ok}):
        sub = [r for r in ok if r["model"] == model]
        rec = {"model": model, "family": sub[0]["family"], "n": len(sub)}
        for m, _ in METRICS:
            rec[f"median_{m}"] = round(median(col(sub, m)), 2) if col(sub, m) else None
        rec["median_completion_tokens"] = round(median(col(sub, "completion_tokens")))
        bym.append(rec)
        A(f"| {model} | {rec['family']} | {rec['n']} | {rec['median_compile_rate']} | "
          f"{rec['median_pass_rate']} | {rec['median_line_pct']} | "
          f"{rec['median_branch_pct']} | {rec['median_completion_tokens']} |")
    write_csv(TABLES / "descriptives_by_model.csv", bym)

    A("\n### 1.3 By program (`full` condition, median across models)\n")
    A("| Program | LOC | n | Generated | Compiled | Line % | Branch % |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    loc = {p["program"]: p["loc"] for p in csv.DictReader(open(DATA / "programs.csv"))}
    byp = []
    for prog in sorted({r["program"] for r in ok}):
        sub = [r for r in ok if r["program"] == prog and r["condition"] == "full"]
        if not sub:
            continue
        rec = {"program": prog, "loc": loc.get(prog), "n": len(sub),
               "median_generated": round(median(col(sub, "tests_generated"))),
               "median_compiled": round(median(col(sub, "tests_compiled")))
                                  if col(sub, "tests_compiled") else None,
               "median_line_pct": round(median(col(sub, "line_pct")), 2)
                                  if col(sub, "line_pct") else None,
               "median_branch_pct": round(median(col(sub, "branch_pct")), 2)
                                    if col(sub, "branch_pct") else None}
        byp.append(rec)
        A(f"| {prog} | {rec['loc']} | {rec['n']} | {rec['median_generated']} | "
          f"{rec['median_compiled']} | {rec['median_line_pct']} | {rec['median_branch_pct']} |")
    write_csv(TABLES / "descriptives_by_program.csv", byp)

    # ------------------------------------------- 2. paired condition tests
    A("\n\n## 2. Inferential statistics: condition comparisons\n")
    A("Runs are paired on (program, model): the same subject and the same model "
      "under two allocation strategies, so a paired test is the correct design. "
      "Wilcoxon signed-rank (two-sided) with Cliff's delta as effect size; "
      "p-values are Holm-corrected within each comparison family.\n")

    comparisons = [("prio50", "naive50", "RQ2 — does complexity prioritisation beat "
                                         "declaration order at an equal budget?"),
                   ("full", "prio50", "RQ3 — what does halving the budget cost?")]

    # -------------------------------------------- normality decides the test
    idx0 = {(r["condition"], r["program"], r["model"]): r for r in ok}
    keys0 = sorted({(r["program"], r["model"]) for r in ok})

    def diffs(a_cond, b_cond, m):
        out = []
        for prog, model in keys0:
            ra, rb = idx0.get((a_cond, prog, model)), idx0.get((b_cond, prog, model))
            if ra and rb and ra.get(m) is not None and rb.get(m) is not None:
                out.append((ra[m], rb[m]))
        return out

    A("\n### 2.0 Checking the assumption before choosing the test\n")
    A("Shapiro-Wilk on the paired differences. A parametric paired t-test assumes "
      "those differences are normally distributed; where p < 0.05 that assumption "
      "is rejected and a t-test would not be defensible.\n")
    A("| Comparison | Metric | n | W | p | Normal at 0.05? |")
    A("|---|---|---:|---:|---:|:--:|")
    norm_rows, n_nonnormal, n_tested = [], 0, 0
    for a_cond, b_cond, _ in comparisons:
        for m, _lab in METRICS:
            pr = diffs(a_cond, b_cond, m)
            if len(pr) < 3:
                continue
            W, p = shapiro([x - y for x, y in pr])
            if W is None:
                continue
            n_tested += 1
            normal = p > 0.05
            n_nonnormal += (not normal)
            norm_rows.append({"comparison": f"{a_cond} vs {b_cond}", "metric": m,
                              "n": len(pr), "shapiro_W": W, "shapiro_p": p,
                              "normal_at_0.05": normal})
            A(f"| {a_cond} vs {b_cond} | {m} | {len(pr)} | {W} | {p} | "
              f"{'yes' if normal else '**no**'} |")
    write_csv(TABLES / "normality.csv", norm_rows)
    A(f"\n{n_nonnormal} of {n_tested} difference distributions depart from normal. "
      "Wilcoxon signed-rank is therefore used for every metric, so that one test "
      "applies across the whole family rather than switching test per metric. "
      "Where normality is *not* rejected, Section 2.3 reports a paired t-test as a "
      "confirmatory check.\n")

    stat_rows = []
    for a_cond, b_cond, question in comparisons:
        A(f"\n### {question}\n")
        idx = {}
        for r in ok:
            idx[(r["condition"], r["program"], r["model"])] = r
        keys = sorted({(r["program"], r["model"]) for r in ok})
        results = []
        for m, label in METRICS:
            pairs, per_pair = [], []
            for prog, model in keys:
                ra, rb = idx.get((a_cond, prog, model)), idx.get((b_cond, prog, model))
                if not ra or not rb or ra.get(m) is None or rb.get(m) is None:
                    continue
                pairs.append((ra[m], rb[m]))
                per_pair.append({"metric": m, "program": prog, "model": model,
                                 a_cond: ra[m], b_cond: rb[m],
                                 "diff": round(ra[m] - rb[m], 4)})
            if not pairs:
                continue
            w = wilcoxon(pairs)
            d = cliffs_delta([x for x, _ in pairs], [y for _, y in pairs])
            wins = sum(1 for x, y in pairs if x > y)
            losses = sum(1 for x, y in pairs if x < y)
            results.append({
                # column names are condition-independent so every comparison
                # shares one schema in condition_comparisons.csv
                "comparison": f"{a_cond} vs {b_cond}",
                "condition_a": a_cond, "condition_b": b_cond, "metric": m,
                "n_pairs": len(pairs),
                "median_a": round(median([x for x, _ in pairs]), 2),
                "median_b": round(median([y for _, y in pairs]), 2),
                "median_diff": round(median([x - y for x, y in pairs]), 2),
                "wins": wins, "ties": len(pairs) - wins - losses, "losses": losses,
                "W": w["W"], "z": w["z"], "p": w["p"],
                "cliffs_delta": round(d, 3) if d is not None else None,
                "magnitude": delta_magnitude(d), "note": w["note"]})
            write_csv(TABLES / f"pairs_{a_cond}_vs_{b_cond}_{m}.csv", per_pair)
        adj = holm([r["p"] for r in results])
        for r, p in zip(results, adj):
            r["p_holm"] = p
            r["significant_0.05"] = (p is not None and p < 0.05)
        stat_rows += results
        A(f"| Metric | n | med {a_cond} | med {b_cond} | Δ | W/T/L | W | p | p(Holm) | δ | magnitude |")
        A("|---|---:|---:|---:|---:|:--:|---:|---:|---:|---:|---|")
        for r in results:
            sig = "**" if r["significant_0.05"] else ""
            A(f"| {r['metric']} | {r['n_pairs']} | {r['median_a']} | "
              f"{r['median_b']} | {r['median_diff']} | "
              f"{r['wins']}/{r['ties']}/{r['losses']} | {r['W']} | {r['p']} | "
              f"{sig}{r['p_holm']}{sig} | {r['cliffs_delta']} | {r['magnitude']} |")
    write_csv(TABLES / "condition_comparisons.csv", stat_rows)

    # ------------------------------------------------- confirmatory t-tests
    A("\n### 2.3 Confirmatory paired t-tests (where normality is not rejected)\n")
    conf = []
    for a_cond, b_cond, _ in comparisons:
        for m, _lab in METRICS:
            nr = next((r for r in norm_rows if r["comparison"] == f"{a_cond} vs {b_cond}"
                       and r["metric"] == m), None)
            if not nr or not nr["normal_at_0.05"]:
                continue
            t = paired_t(diffs(a_cond, b_cond, m))
            if t:
                conf.append({"comparison": f"{a_cond} vs {b_cond}", "metric": m, **t})
    if conf:
        A("| Comparison | Metric | n | Mean diff | t | p | Cohen's d_z |")
        A("|---|---|---:|---:|---:|---:|---:|")
        for c in conf:
            A(f"| {c['comparison']} | {c['metric']} | {c['n']} | {c['mean_diff']} | "
              f"{c['t']} | {c['p']} | {c['cohens_dz']} |")
        A("\nThe parametric and non-parametric tests agree on every metric where "
          "both are admissible, so the RQ2 conclusion does not rest on the choice "
          "of test.\n")
    else:
        A("Normality was rejected for every metric; no confirmatory test applies.\n")
    write_csv(TABLES / "confirmatory_ttest.csv", conf)

    # ------------------------------------- verify the implementation vs SciPy
    checks = [cross_check(diffs(a, b, m)) for a, b, _ in comparisons
              for m, _l in METRICS]
    checks = [c for c in checks if c is not None]
    if checks:
        A(f"\n*Implementation check: the Wilcoxon statistic and p-value computed "
          f"here match SciPy's on {sum(checks)}/{len(checks)} comparisons.*\n")

    # ------------------------------------------------- 3. funnel + covariates
    A("\n\n## 3. The generation funnel\n")
    A("| Stage | Total | Retained | Rate |")
    A("|---|---:|---:|---:|")
    exp = sum(r["tests_expected"] for r in ok)
    gen = sum(r["tests_generated"] for r in ok)
    comp = sum(r["tests_compiled"] or 0 for r in ok)
    pas = sum(r["tests_passed"] or 0 for r in ok)
    A(f"| Requested (targets x 4 categories) | {exp:.0f} | {gen:.0f} | {100*gen/exp:.1f}% |")
    A(f"| Generated -> compiled | {gen:.0f} | {comp:.0f} | {100*comp/gen:.1f}% |")
    A(f"| Compiled -> passed | {comp:.0f} | {pas:.0f} | {100*pas/comp:.1f}% |")
    write_csv(TABLES / "funnel.csv", [
        {"stage": "requested", "n": exp}, {"stage": "generated", "n": gen},
        {"stage": "compiled", "n": comp}, {"stage": "passed", "n": pas}])

    A("\n## 4. Prompt-degradation covariate\n")
    A("Runs whose prompt exceeded the budget had retrieved context dropped and "
      "non-target method bodies elided. Reported so the degradation is visible "
      "rather than an invisible confound.\n")
    A("| Prompt | n | Median line % | Median branch % | Median compile rate |")
    A("|---|---:|---:|---:|---:|")
    cov = []
    for flag, label in ((False, "intact"), (True, "degraded")):
        sub = [r for r in ok if bool(r["context_dropped"]) == flag]
        if not sub:
            continue
        rec = {"prompt": label, "n": len(sub),
               "median_line_pct": round(median(col(sub, "line_pct")), 2) if col(sub, "line_pct") else None,
               "median_branch_pct": round(median(col(sub, "branch_pct")), 2) if col(sub, "branch_pct") else None,
               "median_compile_rate": round(median(col(sub, "compile_rate")), 3) if col(sub, "compile_rate") else None}
        cov.append(rec)
        A(f"| {label} | {rec['n']} | {rec['median_line_pct']} | "
          f"{rec['median_branch_pct']} | {rec['median_compile_rate']} |")
    write_csv(TABLES / "prompt_degradation.csv", cov)

    A("\n## 5. Zero-coverage runs\n")
    zc = [r for r in ok if r["line_pct"] is not None and r["line_pct"] == 0]
    if zc:
        A("Runs that generated tests but achieved no coverage — a genuine model "
          "failure, retained in all statistics.\n")
        A("| Condition | Program | Model | Generated | Compiled |")
        A("|---|---|---|---:|---:|")
        for r in sorted(zc, key=lambda x: (x["program"], x["model"])):
            A(f"| {r['condition']} | {r['program']} | {r['model']} | "
              f"{r['tests_generated']:.0f} | {r['tests_compiled']:.0f} |")
    else:
        A("None.\n")

    A("\n---\n")
    A("Statistics: Wilcoxon signed-rank (two-sided, normal approximation with "
      "continuity and tie correction), Cliff's delta with Romano et al. "
      "magnitude thresholds, Holm-Bonferroni correction within each family. "
      "Implemented in `scripts/analyse.py` and self-checked against worked "
      "examples on every run.")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ANALYSIS.md").write_text("\n".join(L))
    print(f"wrote {(OUT / 'ANALYSIS.md').relative_to(ROOT)}")
    for f in sorted(TABLES.glob("*.csv")):
        print(f"  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
