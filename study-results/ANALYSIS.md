# RAGTestGen — Statistical Analysis

Generated from `results/data/runs.csv` (144 runs; 136 analysable, 8 provider failures excluded).

> **Excluded from all statistics below** (rate limit / network failure, not a model result):
>
> - `naive50` / DiningPhilosopher / qwen3_6_27b
> - `naive50` / Disjoint-Set / qwen3_6_27b
> - `naive50` / RedBlackTree / qwen3_6_27b
> - `naive50` / accountsubtype / qwen3_6_27b
> - `naive50` / atmProject2 / qwen3_6_27b
> - `naive50` / electricitybill / qwen3_6_27b
> - `naive50` / nestedmonitor / qwen3_6_27b
> - `naive50` / vendMach / qwen3_6_27b


## 1. Descriptive statistics

### 1.1 Overall, by condition

| Condition | Metric | n | Mean | SD | Median | IQR | Min | Max |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| full | Format yield (parsed/expected) | 48 | 0.88 | 0.21 | 1.0 | 0.19 | 0.17 | 1.17 |
| full | Compilation rate (compiled/generated) | 48 | 0.82 | 0.34 | 1.0 | 0.12 | 0.0 | 1.0 |
| full | Pass rate (passed/compiled) | 46 | 0.85 | 0.22 | 0.94 | 0.24 | 0.11 | 1.0 |
| full | Line coverage % | 48 | 50.32 | 29.75 | 52.59 | 54.68 | 0.0 | 100.0 |
| full | Branch coverage % | 48 | 41.39 | 34.25 | 33.33 | 54.69 | 0.0 | 100.0 |
| full | Instruction coverage % | 48 | 47.96 | 30.04 | 49.22 | 54.01 | 0.0 | 100.0 |
| prio50 | Format yield (parsed/expected) | 48 | 0.9 | 0.2 | 1.0 | 0.05 | 0.07 | 1.01 |
| prio50 | Compilation rate (compiled/generated) | 48 | 0.85 | 0.3 | 1.0 | 0.01 | 0.0 | 1.0 |
| prio50 | Pass rate (passed/compiled) | 47 | 0.84 | 0.21 | 0.89 | 0.25 | 0.17 | 1.0 |
| prio50 | Line coverage % | 48 | 53.28 | 29.08 | 52.94 | 52.62 | 0.0 | 100.0 |
| prio50 | Branch coverage % | 48 | 44.73 | 35.12 | 34.88 | 60.83 | 0.0 | 100.0 |
| prio50 | Instruction coverage % | 48 | 51.12 | 29.76 | 48.15 | 57.12 | 0.0 | 100.0 |
| naive50 | Format yield (parsed/expected) | 40 | 0.81 | 0.32 | 1.0 | 0.31 | 0.08 | 1.0 |
| naive50 | Compilation rate (compiled/generated) | 40 | 0.89 | 0.28 | 1.0 | 0.0 | 0.0 | 1.0 |
| naive50 | Pass rate (passed/compiled) | 38 | 0.9 | 0.17 | 1.0 | 0.19 | 0.08 | 1.0 |
| naive50 | Line coverage % | 40 | 38.8 | 28.5 | 33.66 | 41.34 | 0.0 | 100.0 |
| naive50 | Branch coverage % | 40 | 29.81 | 31.15 | 25.41 | 50.0 | 0.0 | 100.0 |
| naive50 | Instruction coverage % | 40 | 36.49 | 29.02 | 26.62 | 45.8 | 0.0 | 100.0 |

### 1.2 By model (all conditions pooled)

| Model | Family | n | Compile rate | Pass rate | Line % | Branch % | Tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| gptoss120b | GPT-OSS | 48 | 1.0 | 0.97 | 48.13 | 34.34 | 2505 |
| gptoss20b | GPT-OSS | 48 | 1.0 | 0.88 | 46.85 | 33.33 | 1966 |
| qwen3_6_27b | Qwen3 | 40 | 1.0 | 1.0 | 38.28 | 28.57 | 1734 |

### 1.3 By program (`full` condition, median across models)

| Program | LOC | n | Generated | Compiled | Line % | Branch % |
|---|---:|---:|---:|---:|---:|---:|
| ATMProject | 351 | 3 | 48 | 16 | 21.43 | 25.71 |
| Account | 242 | 3 | 32 | 32 | 61.67 | 30.0 |
| ArrayPartitions | 59 | 3 | 8 | 8 | 100.0 | 100.0 |
| Binary-Search-Tree | 416 | 3 | 44 | 32 | 46.85 | 25.58 |
| BoundedBuffers | 130 | 3 | 28 | 16 | 67.31 | 33.33 |
| CruiseControl | 547 | 3 | 60 | 49 | 78.34 | 71.21 |
| DiningPhilosopher | 62 | 3 | 8 | 8 | 37.5 | 0.0 |
| Disjoint-Set | 102 | 3 | 24 | 24 | 24.0 | 12.5 |
| RedBlackTree | 850 | 3 | 60 | 3 | 18.13 | 11.89 |
| accountsubtype | 256 | 3 | 60 | 43 | 77.46 | 63.64 |
| atmProject2 | 178 | 3 | 32 | 32 | 53.57 | 62.86 |
| clean | 189 | 3 | 28 | 27 | 84.31 | 80.0 |
| deadlocks | 45 | 3 | 8 | 4 | 23.53 | 0.0 |
| electricitybill | 91 | 3 | 12 | 12 | 20.69 | 66.67 |
| nestedmonitor | 149 | 3 | 40 | 40 | 82.35 | 100.0 |
| vendMach | 327 | 3 | 8 | 8 | 56.0 | 57.14 |


## 2. Inferential statistics: condition comparisons

Runs are paired on (program, model): the same subject and the same model under two allocation strategies, so a paired test is the correct design. Wilcoxon signed-rank (two-sided) with Cliff's delta as effect size; p-values are Holm-corrected within each comparison family.


### 2.0 Checking the assumption before choosing the test

Shapiro-Wilk on the paired differences. A parametric paired t-test assumes those differences are normally distributed; where p < 0.05 that assumption is rejected and a t-test would not be defensible.

| Comparison | Metric | n | W | p | Normal at 0.05? |
|---|---|---:|---:|---:|:--:|
| prio50 vs naive50 | yield | 40 | 0.6236 | 0.0 | **no** |
| prio50 vs naive50 | compile_rate | 40 | 0.7536 | 1e-06 | **no** |
| prio50 vs naive50 | pass_rate | 38 | 0.9184 | 0.0088 | **no** |
| prio50 vs naive50 | line_pct | 40 | 0.9543 | 0.106892 | yes |
| prio50 vs naive50 | branch_pct | 40 | 0.9736 | 0.463487 | yes |
| prio50 vs naive50 | instr_pct | 40 | 0.9459 | 0.054654 | yes |
| full vs prio50 | yield | 48 | 0.8214 | 4e-06 | **no** |
| full vs prio50 | compile_rate | 48 | 0.7407 | 0.0 | **no** |
| full vs prio50 | pass_rate | 45 | 0.9217 | 0.004821 | **no** |
| full vs prio50 | line_pct | 48 | 0.8836 | 0.000193 | **no** |
| full vs prio50 | branch_pct | 48 | 0.7579 | 0.0 | **no** |
| full vs prio50 | instr_pct | 48 | 0.8796 | 0.000147 | **no** |

9 of 12 difference distributions depart from normal. Wilcoxon signed-rank is therefore used for every metric, so that one test applies across the whole family rather than switching test per metric. Where normality is *not* rejected, Section 2.3 reports a paired t-test as a confirmatory check.


### RQ2 — does complexity prioritisation beat declaration order at an equal budget?

| Metric | n | med prio50 | med naive50 | Δ | W/T/L | W | p | p(Holm) | δ | magnitude |
|---|---:|---:|---:|---:|:--:|---:|---:|---:|---:|---|
| yield | 40 | 1.0 | 1.0 | 0.0 | 12/28/0 | 0 | 0.00252 | **0.01008** | 0.218 | small |
| compile_rate | 40 | 1.0 | 1.0 | 0.0 | 5/26/9 | 42.0 | 0.52975 | 0.52975 | -0.088 | negligible |
| pass_rate | 38 | 0.88 | 1.0 | 0.0 | 10/11/17 | 111.5 | 0.06402 | 0.12804 | -0.172 | small |
| line_pct | 40 | 52.94 | 33.66 | 14.82 | 25/9/6 | 89.0 | 0.00189 | **0.00945** | 0.321 | small |
| branch_pct | 40 | 34.11 | 25.41 | 15.84 | 25/8/7 | 105.0 | 0.00303 | **0.01008** | 0.241 | small |
| instr_pct | 40 | 48.15 | 26.62 | 11.74 | 26/9/5 | 85.0 | 0.00145 | **0.0087** | 0.314 | small |

### RQ3 — what does halving the budget cost?

| Metric | n | med full | med prio50 | Δ | W/T/L | W | p | p(Holm) | δ | magnitude |
|---|---:|---:|---:|---:|:--:|---:|---:|---:|---:|---|
| yield | 48 | 1.0 | 1.0 | 0.0 | 10/26/12 | 115.0 | 0.72091 | 1.0 | -0.081 | negligible |
| compile_rate | 48 | 1.0 | 1.0 | 0.0 | 8/30/10 | 68.0 | 0.45903 | 1.0 | -0.049 | negligible |
| pass_rate | 45 | 0.94 | 0.89 | 0.0 | 18/12/15 | 257.0 | 0.68101 | 1.0 | -0.009 | negligible |
| line_pct | 48 | 52.59 | 52.94 | 0.0 | 15/17/16 | 210.5 | 0.46838 | 1.0 | -0.066 | negligible |
| branch_pct | 48 | 33.33 | 34.88 | 0.0 | 14/22/12 | 165.0 | 0.79948 | 1.0 | -0.046 | negligible |
| instr_pct | 48 | 49.22 | 48.15 | 0.0 | 15/13/20 | 270.0 | 0.46607 | 1.0 | -0.085 | negligible |

### 2.3 Confirmatory paired t-tests (where normality is not rejected)

| Comparison | Metric | n | Mean diff | t | p | Cohen's d_z |
|---|---|---:|---:|---:|---:|---:|
| prio50 vs naive50 | line_pct | 40 | 15.697 | 3.4272 | 0.001451 | 0.542 |
| prio50 vs naive50 | branch_pct | 40 | 14.762 | 3.1066 | 0.003521 | 0.491 |
| prio50 vs naive50 | instr_pct | 40 | 15.734 | 3.4587 | 0.001328 | 0.547 |

The parametric and non-parametric tests agree on every metric where both are admissible, so the RQ2 conclusion does not rest on the choice of test.


*Implementation check: the Wilcoxon statistic and p-value computed here match SciPy's on 12/12 comparisons.*



## 3. The generation funnel

| Stage | Total | Retained | Rate |
|---|---:|---:|---:|
| Requested (targets x 4 categories) | 4072 | 3274 | 80.4% |
| Generated -> compiled | 3274 | 2451 | 74.9% |
| Compiled -> passed | 2451 | 2080 | 84.9% |

## 4. Prompt-degradation covariate

Runs whose prompt exceeded the budget had retrieved context dropped and non-target method bodies elided. Reported so the degradation is visible rather than an invisible confound.

| Prompt | n | Median line % | Median branch % | Median compile rate |
|---|---:|---:|---:|---:|
| intact | 126 | 49.04 | 34.34 | 1.0 |
| degraded | 10 | 21.2 | 15.73 | 0.116 |

## 5. Zero-coverage runs

Runs that generated tests but achieved no coverage — a genuine model failure, retained in all statistics.

| Condition | Program | Model | Generated | Compiled |
|---|---|---|---:|---:|
| full | ATMProject | gptoss20b | 48 | 0 |
| naive50 | ATMProject | gptoss20b | 32 | 0 |
| full | RedBlackTree | gptoss120b | 60 | 0 |
| prio50 | RedBlackTree | qwen3_6_27b | 7 | 0 |
| naive50 | atmProject2 | gptoss20b | 16 | 0 |

---

Statistics: Wilcoxon signed-rank (two-sided, normal approximation with continuity and tie correction), Cliff's delta with Romano et al. magnitude thresholds, Holm-Bonferroni correction within each family. Implemented in `scripts/analyse.py` and self-checked against worked examples on every run.