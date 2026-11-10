# RAGTestGen — Study Results

Final dataset and statistical analysis. Everything here is **derived**: it is
regenerated from `../runs/` by two scripts and should never be hand-edited.

```
scripts/aggregate.py   runs/**/{gen,eval}.json  ->  results/data/*.csv
scripts/analyse.py     results/data/runs.csv    ->  results/tables/*.csv + ANALYSIS.md
```

Reproduce the whole folder:

```bash
python3 scripts/aggregate.py && python3 scripts/analyse.py
```

## Contents

| Path | What it is |
|---|---|
| `ANALYSIS.md` | The narrative report: descriptives, hypothesis tests, funnel, covariates. Start here. |
| `data/runs.csv` | **The analysis unit.** One row per (condition x program x model) = 144 rows. |
| `data/tests.csv` | One row per generated test case (3274) with its execution status and coverage. |
| `data/programs.csv` | The 16 benchmark subjects with LOC and pre-existing test counts. |
| `data/manifest.json` | Provenance: model config, control variables, derived-column formulas, environment, gaps. |
| `tables/*.csv` | Paper-ready tables, one per result. |
| `tables/pairs_*.csv` | Every individual paired difference behind each hypothesis test. |

## Traceability

Any number in the paper can be walked back to the artefact it came from:

```
ANALYSIS.md  ->  tables/*.csv  ->  data/runs.csv  ->  run_dir  ->  raw.txt / suite.exec
```

Each row of `runs.csv` carries `run_dir` plus `gen_sha256` and `eval_sha256`, so
the source files can be identified and verified as unmodified. Inside a run
directory:

- `raw.txt` — the verbatim, unparsed model response
- `gen.json` — targets, per-batch prompt/latency/token accounting, parsed tests
- `testsrc/`, `testclasses/` — the Java actually written and compiled
- `exec/t*.exec`, `suite.exec` — JaCoCo binary execution data
- `eval.json` — compile log, per-test status, coverage

Coverage percentages are independently verifiable without this pipeline:

```bash
java -jar lib/jacococli.jar report runs/full/<prog>__<model>/suite.exec \
  --classfiles bench/<prog>/classes --csv /tmp/verify.csv
```

## Reading the data honestly

**`status` is not decoration.** Filter on it before computing anything.

- `ok` — generated and compiled; include everywhere
- `no_compile` — the model produced tests, none compiled. A **real result**; keep it
- `no_tests` — the request never reached the model (rate limit / network). **Not a
  result**; excluded from every statistic in `ANALYSIS.md` and listed in
  `manifest.json` under `integrity.gaps`

**Known gap.** 8 `naive50` / qwen3_6_27b runs are missing: Groq's 200k
tokens-per-day cap was exhausted. These are non-random (all one model in one
condition), so the RQ2 comparison rests on 40 of 48 pairs. Refill with:

```bash
python3 scripts/run_study.py --condition naive50 --models qwen3_6_27b
```

then re-run both scripts. Runs that already hold tests are cached and will not
be regenerated.

**Generation is stochastic** (`temperature=0.2`). Re-running produces different
suites; the archived `runs/` directory is the record of what was measured.

## Design

3 conditions x 3 models x 16 programs = 144 runs.

- **Conditions** — `full` (up to 15 methods by complexity), `prio50` (half the
  budget, most complex first), `naive50` (half the budget, declaration order).
  `prio50` vs `naive50` isolates prioritisation at a fixed budget.
- **Models** — gpt-oss-120b, gpt-oss-20b (Groq), qwen3.6-27b (Groq).
- **Held fixed** — prompt template, temperature 0.2, 4 tests/method, retrieval
  (500-char chunks, stride 400, top-10, all-MiniLM-L6-v2).

Tests are paired on (program, model) and non-parametric throughout: Wilcoxon
signed-rank, Cliff's delta, Holm-Bonferroni within each family. The statistics
are implemented in `scripts/analyse.py` with self-checks against worked examples
that run on every invocation.
