# Planner v0.4 derived audit

This audit uses a **made-up** student profile: $3,000 total savings, $2,000
protected outside the pot, $1,000 initially invested, and $100/month for 60 months.
These numbers do not represent the user. All monetary results exclude taxes.

- 18 future cases: six allocations × three excess-return assumptions.
- Six sensitivity cases for the risk-balanced candidate: 3/6/12-month blocks,
  full input sample versus the last ten years.
- 18 daily historical replays: six candidates × three stress episodes.
- Every event-specific ERC fit uses 756 earlier observations; dates and
  first-order errors are in `causal_model_fits.json`.
- `historical_replays.csv` reports cumulative TWR and dollar P&L separately.
  Its annualized XIRR column is explicitly an audit field; the app converts it
  to the replay's own total period for comparison with cumulative TWR.

Non-wrapping blocks underweight sample boundary months. The zero-premium case
centers the **conditional eligible-month distribution at each block position**,
not the realized simulated paths. Expected excess log return is zero at every
position; finite draws need not average exactly zero. All allocations within a
case use identical sampled months and external cash flows. Historical covariance
uses longer SPY/GLD/IEF history; the four-asset performance sample still starts
in 2007. Future covariance fits overlap the resampling input. This is descriptive
model checking, not new independent validation or a prospective trading record.

The risk-balanced candidate is a convex equal-risk-contribution solve on a
positive definite, diagonally shrunk covariance. The cash share is fixed by the
example, and a same-cash/equal-risky-capital control is included. This objective
does not maximize returns or establish suitability, and does not claim to beat
the controls. Inspect the CSVs rather than interpreting one scenario as a forecast.

See [the implementation contract](../../docs/BUDGET_PLANNER.md). The manifest
hashes numeric source, input snapshot and exported tables. No daily prices or
paper PDFs are redistributed.
