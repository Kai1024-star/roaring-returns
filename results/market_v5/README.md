# Multi-asset conditional model audit

These derived tables use a **made-up** account: $1,000 investable initially,
$100 added per modeled month, 2bp per risky purchase/sale, and fractional
holdings. They do not contain entered user budgets or raw provider time series.

- 32 cases: core 9 / extended 13 funds × two generators × four allocations
  × 12 / 36-month horizons, each with 1,000 simulated daily paths.
- Fixed 10% cash, at least 40% equities, 45% single risky-fund cap, 20% combined
  commodity cap and 10% oil cap for constrained allocations. The class example
  has predetermined asset-class shares instead of an optimized objective.
- Default retained excess log mean 25%, annual cash assumption 3%, 21-session
  blocks/months, and evaluation seed 20261022.
- Calibration is the available common history through 2026-10-22, requested
  as 20 years; the snapshot has 4,842 sessions beginning 2007-07-26.
- `summary.csv` separates ending wealth, dollar investment P&L, cumulative
  flow-neutral returns, drawdown and fees. No method is promoted as superior.
- `weights.csv` exposes each allocation. The CVaR optimizer uses every overlapping
  21-session historical window, independent of the path generator and without
  training-window random selection. CVaR is a one-month model objective.
- `scenario_groups.csv` contains 128 descriptive group records, with counts,
  shares and actual member representatives. Largest counts do not establish
  real-world probabilities or a uniquely most-likely future. Groups depend on
  the feature definition, number of groups and simulated sample.
- `calibration.json` records the earlier daily and completed-week observation
  ranges. `data_manifest.json` records provenance/hashes and same-provider audit
  diagnostics, without redistributing prices. `manifest.json` hashes all numeric
  dependencies and derived artifacts; the offline checker verifies them.

All variants reuse the same underlying historical information. Different
generators change assumptions; more paths do not create independent market data.
The raw covariance is preserved by default, apart from a minimal positive-definite
conditioning floor if needed. A one-month downside objective, low estimated
variance, a representative path and a multi-year account outcome answer different
questions. None is an investment recommendation or a future loss guarantee.

See the [method contract](../../docs/MARKET_SIMULATOR.md). Reproduce after an
explicit data fetch with `python scripts/export_market_audit.py`; it refuses to
overwrite an existing export. Verify offline with `python scripts/check_market_audit.py`.
