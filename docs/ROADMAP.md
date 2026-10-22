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
