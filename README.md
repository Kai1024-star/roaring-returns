# Roaring Returns

[![Offline research checks](https://github.com/Kai1024-star/roaring-returns/actions/workflows/tests.yml/badge.svg)](https://github.com/Kai1024-star/roaring-returns/actions/workflows/tests.yml)

A Python personal research project on contribution-aware portfolio rebalancing
and convex optimization under execution risk.
It includes an English budget-first educational homepage and an advanced research lab.
The research question is how allocation drift and required selling change with
monthly contributions relative to wealth. The focus is portfolio implementation: allocating new cash, measuring drift,
and quantifying unavoidable sales under explicit assumptions.

## Budget planner and research demo (v0.4)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[demo,validation]'
.venv/bin/python -m roaring_returns demo
```

Open **http://127.0.0.1:8501**. The synthetic market works offline without keys.
Start on **Budget planner**: separate protected cash, enter monthly saving and
a time horizon, then compare fixed examples, a custom mix and a solved risk-balanced
candidate. The main chart separates **investment P&L**, **returns excluding deposits**,
and **account balance**, with a daily return-drawdown panel and cash benchmark.
A rising balance from deposits is no longer presented as investment performance.

![Investment performance and drawdown](docs/demo/budget_v4_performance.jpg)

The model uses joint whole-month blocks with daily valuation, three explicit
excess-return assumptions and a 3/6/12-month × two-window sensitivity grid.
The risk-balanced candidate solves a convex equal-variance-contribution problem;
it has a same-cash/equal-risky-weight control, verified first-order conditions,
and strictly pre-event covariance estimates for historical stress. It does not
optimize an expected-return forecast or select a suitable investment for a user.

- [v0.4 model, accounting and limitations](docs/BUDGET_PLANNER.md)
- [42 derived demonstration checks and source hashes](results/planner_v4/README.md)
- [Risk-balancing demo preview](docs/demo/budget_v4_optimizer.jpg)
- [Scenario and sensitivity demo preview](docs/demo/budget_v4_scenarios.jpg)
- Offline artifact check: `python scripts/check_planner_audit.py`

For historical homepage inputs, run:

```bash
.venv/bin/python -m roaring_returns fetch-planner
```

This creates a separate SPY/GLD/IEF/BIL snapshot (common local coverage:
2007-05-30–2025-12-31). Cash and inflation remain editable assumptions. Future
risky scenarios use historical excess log returns over BIL plus the same cash
anchor used for the savings reference. Historical replay and sampled scenarios
are valued daily, with contributions and trading at month ends. Without this cache the homepage clearly labels its
synthetic demonstration. [Read the planning contract and limitations](docs/BUDGET_PLANNER.md).

Switch to **Research lab** for the original execution-risk workspace.
Inspect frozen dollar orders, change next-session prices, and compare realized
drift, selling and fees. A causal ridge volatility model is compared with EWMA;
it forecasts execution uncertainty, not alpha. CVXPY/Clarabel solve cost-aware
and tail-risk-budget allocation programs. OSQP is a disclosed tie-break retry.

![Execution-risk demo](docs/demo/execution_lab.jpg)

- [v0.2 methods, assumptions and code provenance](docs/EXECUTION_RISK_V2.md)
- [ETF execution-risk findings](results/execution_v2/README.md) and
  [synthetic mechanism results](results/execution_v2_synthetic/REPORT.md)
- [Paper-to-implementation boundaries](docs/paper_implementation_map.csv)

The new study uses 12 methods × 3 historical windows, with common 2bp costs.
It is exploratory: the history was already inspected. Finite-scenario CVaR
is not a market coverage guarantee, and ML is not assumed to improve outcomes.
The original five-rule v0.1 results below remain separate and unchanged.

In 2020–2025, signal minimum sale finished outside the band in 10/72 months;
the EWMA risk-budget planner did so in 1/72, with annual sales increasing from
0.77% to 1.17% of mean wealth. The analytic buffer also achieved 1/72.
Ridge volatility QLIKE was worse than EWMA in all three ETF windows, so the
project preserves a negative ML result rather than claims learned superiority.

Reproduce the new study with `python -m roaring_returns research --source synthetic`,
or `--source yahoo` after fetching the cached snapshot. The tested package
versions are in `constraints-demo.txt`.
Runs and public exports refuse to overwrite existing folders. Public numeric
artifacts can be checked offline with `python scripts/check_v2_exports.py`.

![Historical comparison](results/period_comparison.png)

## Results and research notes

- [Historical results and figures](results/README.md): 2005–2014 development,
  2015–2019 validation, and 2020–2025 retrospective evaluation.
- [Mathematical derivations](docs/MATHEMATICS.md): exact cash requirements,
  purchase-only projection, and the static minimum-sale bound.
- [Protocol](docs/RESEARCH_PROTOCOL.md), [AI-assisted review](docs/REVIEW_LOG.md),
  and [next increments](docs/ROADMAP.md).

Each historical segment has 45 main cases, 15 band-sensitivity cases, and five
cost-stress cases. Results are descriptive, without statistical confidence
intervals or a prospective trading record. Parameters remain unchanged across
segments. There is no claim of alpha, novelty, or universal superiority.

For the USD 10,000 + USD 100/month account, the 5pp minimum-sale plan used
less selling but had greater drift than a 5pp center reset in every segment.
Across different widths that summary changes: 2pp minimum-sale cases had lower
RMS and lower dollar sales than 5pp center resets, while selling more often.
[Read the counts, overshoot sizes, and cash-flow results](results/README.md).

## Quick start

Use Python 3.11 or later. From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[validation]'
.venv/bin/python -m roaring_returns fetch
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m roaring_returns run --split development
.venv/bin/python -m roaring_returns run --split validation
.venv/bin/python -m roaring_returns run --split evaluation
.venv/bin/python scripts/publish_results.py
```

If the dependencies already exist in your environment, use
`PYTHONPATH=src python3 -m roaring_returns run --split development` and
`PYTHONPATH=src python3 -m unittest discover -s tests -v`.

Data acquisition needs an internet connection. After `fetch` succeeds, tests and
experiments work offline against the cached, hashed snapshot. `fetch --refresh`
explicitly replaces the provider snapshot. Do not silently change data between
experiments. A `.venv` is recommended; no credentials belong in the repository.

## Current implementation

- Public Yahoo Finance daily data for QQQ, GLD and IEF, with raw JSON snapshots,
  vendor daily fields, actions, a common-calendar audit and SHA-256 manifests.
- Normalized adjusted-close **return-unit proxies**, not executable share prices.
- Five allocation rules and the static minimum-sale bound checked against LP/QP solvers.
- A daily holdings/cash ledger, monthly external contributions, explicit lagged
  dollar plans, cash-constrained execution, proportional fee stress, and TWR.
- A frozen configuration covering 45 wealth/contribution/strategy scenarios per
  chronological segment, plus representative-account band sensitivity (2/5/10pp)
  and a separate 10bp stress case.
- CSV results, representative account ledgers, figures, a research report, and
  meaningful mechanism/accounting/no-lookahead tests.

## Timing contract

Initialize at the last session before the requested segment. At the end of each
month, compute next month's dollar trade plan from that completed session's
holdings. The next observed session's existing positions earn that day's return;
the external contribution arrives at that session's close, then the frozen
dollar orders execute. The contribution amount is fixed dollars, or a declared
fraction of signal-date wealth. Execution-day returns cannot select the plan.

TWR for a contribution/execution day is the product of:

1. pre-flow marked wealth / previous close wealth;
2. post-trade wealth / (pre-flow marked wealth + external contribution).

For costs, sells are capped by available holdings and buys are reduced to keep
cash nonnegative. Fees are charged on actual gross purchases and sales. Initial
investment costs count in NAV. Costs do not generate extra contributions.

The ±5pp band and minimum-sale bound describe a frictionless SIGNAL-state
optimization. Delayed or cost-adjusted fills may finish outside the band. The
reports measure realized deviations rather than assert perfect restoration.
Main comparisons use pre-trade deviation on common signal dates, post-trade
deviation on common execution dates, and selling. Daily outside-band time is a
secondary exposure metric. `events_*.csv` records each asset's planned and actual
trade, both wealth denominators, cash requirements and post-fill compliance.

## Data and scope limits

Yahoo adjusted-close ratios are used as a total-return proxy with implicit
reinvestment in the original asset. Dividends are **not** added again as cash.
Downloaded action fields support auditing, not a claim to have payment dates or
a complete corporate-action ledger. No whole-share, tax-lot, or tax-savings
claims are made. Cash earns zero in the original research ledger; the separate
budget planner uses an explicit user-supplied interest assumption. Market impact
is omitted. This is a prototype,
not a certified data feed or a brokerage execution simulator.

The ETF universe is selected retrospectively. The default target is equal
weights, not a historical optimized allocation. Return is secondary to drift
and selling. Zero selling for a buy-only rule is imposed by construction. The
minimum-sales rule is a single-state objective, not a global dynamic optimum.

`configs/baseline.json` fixes a development segment (2005–2014), validation
(2015–2019), and final retrospective evaluation (2020–2025). They are independent
funded-start case studies, not a stitched continuously funded account. Use
`--split validation` or `--split evaluation` explicitly. All three segments have now been run with the same baseline. No parameter
tuning should use the final evaluation. Publicly known
history is not a prospective untouched test.

Data are cached locally for personal research. Raw vendor data are ignored by
Git; verify licensing before redistributing any dataset. A shareable repository
should contain the downloader and synthetic fixtures, not someone else's data.

## Files

- `src/roaring_returns/data.py`: fetch, parse, validate, cache and hash.
- `src/roaring_returns/policies.py`: buy-only and minimum-sale allocation.
- `src/roaring_returns/engine.py`: daily ledger and contribution-safe performance.
- `src/roaring_returns/experiments.py`: declared scenarios, reports and plots.
- `tests/test_research.py`: independent LP and accounting checks.
- `results/`: published aggregate reports, tables, figures, and hash manifests.
- `reports/runs/`: local full outputs, including detailed ledgers (Git-ignored).
- `scripts/publish_results.py`: reproducible aggregate-only export.
- `scripts/verify_cashflow_bounds.py`: original static-mechanism check, including
  2,001 LP comparisons across two to six assets; run it with Python after installing
  the validation extra.
- `.github/workflows/tests.yml`: offline test matrix on Python 3.11 and 3.12.
- `notebooks/01_explore.ipynb`: read and visualize generated results.
- `docs/RESEARCH_PROTOCOL.md`: frozen assumptions and review record.

## Next data upgrade

For actual historical whole-share trading and spendable dividend cash, obtain
per-share prices, split factors, amounts, ex-dates and payment dates from a
verified source. Columbia's [WRDS access guide](https://guides.library.columbia.edu/WRDS/overview)
and [subscription list](https://guides.library.columbia.edu/WRDS/collection) are
the first resources to check. Public data are sufficient to run this fractional
prototype; a Columbia login is not currently required.

## Reproducibility and authorship

The observed numerical environment is recorded in `docs/environment.json`.
Run manifests hash each source module, protocol, and processed snapshot; public
artifact hashes are in `results/artifact_hashes.json`. Exact results require the
original data hash, since a later public download may revise adjustments. CI
uses synthetic paths and independent optimization checks, with no data login.

Developed with AI assistance: Codex implemented the prototype and Claude
provided an independent code/method review, recorded with findings and fixes.
That review is not data certification or independent institutional validation.

Raw vendor data are not redistributed. Source availability does not grant
rights to a third party's market data. No software license is selected yet.

The public chart endpoint is unofficial and can change or rate-limit requests.
Check the provider's terms for your intended use. TWR neutralizes external-flow
timing; actual investor dollar outcomes differ and money-weighted returns are
not computed. Ten basis points is charged on each purchase and sale amount in
the stress case; it is an experimental assumption, not a brokerage quote.
