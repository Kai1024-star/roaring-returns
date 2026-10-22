# Research roadmap

## Implemented v0.1

- Single-state cash requirement, purchase-only projection, minimum-sale band rule.
- Daily fractional total-return-unit ledger with lagged plans and external flows.
- Five controls, 45 scenarios per historical segment, band and cost sensitivity.
- Independent optimization, conservation, TWR, scale, and no-lookahead tests.
- Local hashed provider snapshots; aggregate reports suitable for public review.

## Next research increments

1. Cash-flow reachability calibration: distinguish reset-to-target identities
   from actual carried-drift states; freeze a forecast before evaluating it.
2. Paired joint-asset block bootstrap, with dependence-aware intervals. Do not
   treat account scenarios on the same path as independent market samples.
3. A separate recent-period case through the last completed session, with its
   own data snapshot; no silent replacement of the 2005–2025 baseline.
4. Verified tradeable prices, split factors and distribution payment dates,
   then actual-share accounting and a whole-share experiment. Investigate
   Columbia WRDS/CRSP eligibility if public sources cannot meet that contract.
5. Additional asset proxies and lagged covariance-aware tracking objectives,
   evaluated under a newly documented protocol.

Do not select the winning historical band or target from evaluation results.
This version has no tax model, return forecast, confidence-interval claim, or
prospective trading record. Fewer sales alone do not establish tax savings.
