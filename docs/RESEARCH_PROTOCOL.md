# First implementation protocol — 2026-10-22

Personal Python project. This document supersedes the earlier design memo's
proposed execution convention: the implemented convention is previous-close
dollar planning and next-session **close** execution.

## Locked baseline before the first development run

- Assets: QQQ, GLD, IEF; fixed equal-weight target.
- Monthly review; ±5 percentage-point band; no return forecast or parameter fit.
- Representative-account width sensitivity uses 2/5/10pp, specified in the
  preceding design memo, with no selection of a winning historical width.
- Wealth/contribution grid and chronological periods: `configs/baseline.json`.
- Five rules, identical cash-flow dates; no forced terminal liquidation.
- Zero-cost baseline; separately declared 10bp one-way proportional-cost stress
  for the USD 10,000 initial / USD 100 monthly representative account.
- Prices: one cached public Yahoo chart snapshot, USD, daily adjusted closes.
  Research levels are normalized return units. No claim of executable share
  prices or distribution payment dates; no separate dividend cash.
- Initial account invested at the preceding-session close. Subsequent external
  contributions begin at the first session of each new month.
- The ledger marks old holdings through execution-day returns before receiving
  the contribution. Both contributions and costs are handled in the unitized NAV.
- Cash has zero interest; liquidity is idealized; no taxes, whole shares, or impact.
- Main drift comparisons use shared signal dates and execution dates. Daily
  outside-band time remains a secondary exposure measure; boundary and center
  policies need not have the same daily probability of crossing their own band.

## Review record

Codex implemented the downloader, analytic policies, daily engine, scenarios,
plots and tests. Claude reviewed the scope/timing/test design,
then was asked to read the actual source files and run tests without edits.
Any code findings and their dispositions are recorded in `REVIEW_LOG.md`.

The contribution-date TWR convention is the product of market growth before the
external flow and the execution-cost factor after it. It is not the shortcut
`(end_value - contribution) / previous_value`, which assigns post-contribution
fees differently. A unit issuance example tests the implemented convention.

The frictionless minimum-sale expression and its target-distance tie-break are
cross-checked against independent LP/QP formulations. A delayed cost-adjusted
fill is reported as a **minimum-sale plan**, not a dynamic optimum.

## What the first run does and does not establish

Development results describe 2005–2014. A small historical comparison can debug
and illustrate a mechanism; it does not establish universal superiority or new
alpha. Individual sessions and different accounts on one path are dependent.
Validation and evaluation are explicit, separate commands. The initial delivery
leaves them unrun. The data download and quality audit span their dates but do
not select a strategy from their investment outcomes.

Run folders include protocol/data snapshots and code hashes. Preserve a run
before changing assumptions; rerunning the same segment replaces its output.
Do not label retrospective, publicly known history as genuinely unseen future
evidence. If final-evaluation outputs influence a change, disclose it and use a
new evaluation plan rather than relabeling the old data as untouched.

## Data quality checks and remaining upgrade

The downloader rejects mismatched calendars, duplicate sessions, nonpositive or
missing prices and changed cache hashes. The same-provider corporate-action
check compares adjusted-close growth against `(close + ex-date distribution) /
previous_close`, recognizing different reinvestment conventions. It flags gross
errors, not certifies the provider. Raw downloaded actions are retained locally.

For the next version, request verified actual-share prices, split factors,
distribution ex-dates and pay dates. Then replace the implicit reinvestment
proxy with a cash/receivables ledger. CRSP/WRDS is a candidate, not an asserted
existing entitlement; the public prototype does not need it to run.

## Subsequent chronological runs — 2026-10-22

Validation (2015–2019) is a second descriptive stability case; no tuning or
model selection is performed on it. Evaluation (2020–2025) is the final
retrospective case. All source modules and baseline parameters remain those
of the development run. Code/protocol/data hashes identify that frozen state,
which predates Git initialization. The documentation was updated afterwards
to record completed runs. This is not a prospective pre-registration.

The configuration's bootstrap_seed is reserved and unused in v0.1; bootstrap
confidence intervals and a reachability forecast remain unimplemented. Width
values were in the early design, but width analysis was added after the first
development run, before the later segment outcomes were inspected.
