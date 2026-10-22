# Research roadmap

## Implemented v0.1

- Single-state cash requirement, purchase-only projection, minimum-sale band rule.
- Daily fractional total-return-unit ledger with lagged plans and external flows.
- Five controls, 45 scenarios per historical segment, band and cost sensitivity.
- Independent optimization, conservation, TWR, scale, and no-lookahead tests.
- Local hashed provider snapshots; aggregate reports suitable for public review.

## Implemented v0.2

- Cost-aware and filtered-scenario tracking QPs, plus a risk-budget sales LP
  with a transparent tracking tie-break and disclosed solver retries.
- A causal ridge next-session volatility model, EWMA/historical ablations, and
  an inexpensive analytic execution-lag buffer.
- Matched 36-case ETF and 36-case synthetic studies, common warm-up/fees, and
  conditional paired monthly block intervals (not full path-level inference).
- A four-tab local Python demo, downloadable plans, model scores, paper/code
  provenance, and verified numerical/public-artifact hashes.
- Negative ML findings preserved; v0.1 numerical ledger/results remain separate.

## Implemented v0.3

- English budget homepage with protected cash, reserve-gap funding, editable
  monthly saving, horizon, goal and dollar loss-comfort marker.
- Four fixed allocation examples, joint monthly block scenarios with a common
  cash/excess-return anchor, and daily-close historical stress with monthly trades.
- Replay/pause/reset and keyboard timelines, scenario comparisons, explicit
  nominal/today-dollar units, and an opt-in local JSON download.
- Separate SPY/GLD/IEF/BIL snapshot and clearly labeled offline synthetic fallback;
  advanced ML/optimization stays in the research workspace.
- [Planning contract and limitations](BUDGET_PLANNER.md); original research
  numerical-module and public-result hashes remain unchanged.

## Implemented v0.4

- Investment P&L, unitized cumulative returns, percentage drawdown and same-period
  money-weighted returns, with dollar/fee/asset-P&L reconciliation.
- Joint non-wrapping whole-month blocks valued at daily closes, three explicit
  premium assumptions, exact sampler-aware zero-premium centering, and a
  block-length × sample-window sensitivity grid.
- A convex equal-risk-contribution candidate with verified first-order conditions,
  a same-cash/equal-risky-capital control, and strictly causal pre-event estimates.
- Source-aware cache invalidation, cash-flow-date purchasing-power accounting,
  small-fee precision, switchable animated performance views and keyboard playback.
- [42-case derived planner audit](../results/planner_v4/README.md), code/table
  hashes, SciPy optimizer cross-checks and original-research hash preservation.

## Next research increments

1. Cash-flow reachability calibration: distinguish reset-to-target identities
   from actual carried-drift states; freeze a forecast before evaluating it.
2. Full refit/path-level paired joint-asset block bootstrap. Do not
   treat account scenarios on the same path as independent market samples.
3. A separate recent-period case through the last completed session, with its
   own data snapshot; no silent replacement of the 2005–2025 baseline.
4. Verified tradeable prices, split factors and distribution payment dates,
   then actual-share accounting and a whole-share experiment. Investigate
   Columbia WRDS/CRSP eligibility if public sources cannot meet that contract.
5. Multi-period contribution/execution planning and calibrated covariance
   forecasts, followed by an end-to-end learning experiment only if the simpler
   baselines justify it. Freeze a new protocol before prospective shadow tests.

Do not select the winning historical band or target from evaluation results.
This version has no tax model, expected-return forecast, end-to-end inferential
confidence claim, or prospective trading record. Fewer sales alone do not
establish tax savings.
