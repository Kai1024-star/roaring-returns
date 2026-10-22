# What the execution-risk study shows

This is a retrospective application study, with **no claim of alpha, novelty or
untouched out-of-sample validation**. All methods see the same fixed target,
USD 10,000 initial funding, USD 100/month, 5pp band and 2bp fees. The requested
first window starts trading after 252 sessions of risk warm-up (account funded
2005-12-30; 108 monthly fills). Later windows contain 60 and 72 monthly fills.

The final study contains 36 ETF configurations and a separate 36-case synthetic
mechanism study. The generated [report](REPORT.md), [summary](summary.csv),
[variance diagnostics](risk_diagnostics.csv), and
[paired descriptive intervals](paired_intervals.csv) contain the full results.

For **2020–2025**, compare all four controls, rather than only the best row:

| Method | Post-fill RMS (pp) | Outside band / months | Annual sales / mean wealth | Selling months |
| --- | ---: | ---: | ---: | ---: |
| Signal minimum sale | 2.513 | 10/72 | 0.767% | 11 |
| Analytic lag buffer | 2.351 | 1/72 | 1.074% | 14 |
| Risk-budget sales / EWMA | 2.332 | 1/72 | 1.169% | 14 |
| Risk-budget sales / ridge | 2.290 | 0/72 | 1.229% | 12 |

Execution-risk planning reduces violations in this historical segment, while
selling more. The analytic buffer achieves much of the effect with a simpler
model. The risk-budget method is not a dynamic optimum and does not constrain
drift between monthly executions.

**ML negative result:** ridge's variance QLIKE is worse than EWMA in all three
ETF periods (lower is better):

| Requested window | EWMA QLIKE | Ridge QLIKE |
| --- | ---: | ---: |
| 2005–2014, after warm-up | -8.166 | -7.675 |
| 2015–2019 | -8.813 | -8.504 |
| 2020–2025 | -8.296 | -7.989 |

Ridge does not uniformly reduce band violations either: the first window has
3/108 versus EWMA's 2/108, the middle window ties at zero, and the last has
0/72 versus 1/72. A noisier/worse variance forecast can still produce a better
realized decision on one path; that is not reliable evidence of model superiority.
No model or hyperparameter was selected from these displayed scores.

The tracking QPs produce much lower drift, but they trade near the center and
sell approximately 8.4–12.7% of mean wealth per year. Forecast variants are
nearly identical at these settings; squared frozen-dollar tracking is weakly
sensitive to covariance when tail constraints are inactive. Their lower drift
is not an apples-to-apples minimum-sale improvement.

**Numerics are visible:** ETF runs required 28 same-program OSQP tie-break
retries, all completed. The synthetic study required 22 retries, with two
verified first-stage LP-only solutions; those two months lack a completed
nearest-target selection. Soft risk-budget slack, solver status, fill
adjustments and clip counts are retained in the local event files and aggregate
summaries. The CVaR budget is a finite-scenario preference, not a future-market
coverage guarantee.

The initial tracking-QP experiment motivated adding the risk-budget objective
and the analytic comparator. Claude's review then identified scenario filtering
and micro-sale defects. These were fixed before the final complete runs; the
design process was exploratory, not a prospective preregistration. Earlier
generated runs remain locally archived. No historical parameter grid search was
performed; this does not remove researcher choice or hindsight bias.

Run `python scripts/check_v2_exports.py` to verify artifact hashes, numerical
source hashes and monthly-to-summary consistency without downloading data.
The paper-to-code boundaries and mathematical assumptions are in
[the method note](../../docs/EXECUTION_RISK_V2.md).
