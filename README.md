# RAGTestGen

RAGTestGen generates JUnit 5 test suites for Java programs with a large language model. It reads the program with the Java compiler's own parser, chooses which methods to test by cyclomatic complexity, retrieves the most similar source fragments from a vector index and places them in the prompt, then compiles, runs and measures the generated tests with JaCoCo.

This repository holds the tool and the study scripts. The benchmark programs, the 144 raw runs and the derived dataset are kept in a separate private repository ([`ragtestgen-study-data`](https://github.com/Jamaludiin/ragtestgen-study-data)) because the programs come from third-party collections and the runs are large.

## How it works

Six stages, each a function in `ragtestgen/`:

| Stage | Module | What it does |
|---|---|---|
| 1. Static analysis | `analyze.py`, `java/JavaAnalyzer.java` | Recovers every method with signature, visibility and cyclomatic complexity from the compiler's syntax tree (`com.sun.source`). |
| 2. Method selection | `pipeline.py` | Orders methods and cuts to the budget. Strategies: `full`, `prio50` (top half by complexity), `naive50` (first half in file order). |
| 3. Indexing | `retrieval.py` | Splits sources into 500-character pieces with a 400-character step, embeds them with all-MiniLM-L6-v2, stores them in ChromaDB. |
| 4. Retrieval | `retrieval.py` | Returns the 10 pieces most similar to the target method bodies. |
| 5. Generation | `prompts.py`, `llm.py`, `pipeline.py` | One prompt per batch of four methods, four test categories per method (typical, boundary, error, special); parses the answer, with a fallback parser; reduces the prompt when it exceeds the provider limit. |
| 6. Compile and measure | `harness.py`, `java/CoverageBatch.java` | Compiles with `javac`, drops tests that fail to compile and recompiles, runs each test alone under the JaCoCo agent, reports line, branch and instruction coverage. |

Any model behind an OpenAI-compatible chat endpoint can be used. Models are registered in `ragtestgen/config.py`.

## Requirements

- Python 3.10 or newer, and `pip install -r requirements.txt`
- A JDK with `javac` and `java` on the path (tested with JDK 22)
- API keys for the providers you use, in `.env` (see `.env.example`). `.env` is ignored by git.

The jars in `lib/` (JUnit, Hamcrest, JaCoCo, ASM) are included; see `lib/THIRD_PARTY.md`.

## Running the study

```bash
# 1. Curate programs: one sub-directory per Java program; compiles each and records why any was excluded
python3 scripts/curate.py --source /path/to/programs --dest bench

# 2. Screen candidate models for availability and format compliance
python3 scripts/screen_models.py

# 3. Run the study: 3 strategies x registered models x programs, results in runs/<condition>/<program>__<model>/
python3 scripts/run_study.py --condition full
python3 scripts/run_study.py --condition prio50
python3 scripts/run_study.py --condition naive50

# 4. Aggregate runs into results/data/*.csv, then analyse into results/tables/*.csv and ANALYSIS.md
python3 scripts/aggregate.py && python3 scripts/analyse.py
```

Each run directory contains the raw model answer (`raw.txt`), the parsed tests (`testsrc/`), the compiled classes, the JaCoCo execution file (`suite.exec`), and `gen.json` / `eval.json` with every count the paper reports. A run is marked `no_tests` when the request never reached the model (rate limit or network); such runs are excluded from the statistics and listed in `results/data/manifest.json`.

## Statistics

`scripts/analyse.py` implements the paired Wilcoxon signed-rank test with continuity and tie correction, Cliff's delta, the Holm-Bonferroni adjustment, the Shapiro-Wilk check and a confirmatory paired t-test. Each procedure is checked against a worked example on every run and compared with SciPy.

## Citation

See `CITATION.cff`. The accompanying paper is under review; the entry will be updated with the DOI.

## Licence

MIT, see `LICENSE`. Third-party jars keep their own licences.
