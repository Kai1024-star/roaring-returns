# Budget planner v0.4: money, investment performance and risk

The English homepage separates deposits from investment performance and includes
an explicit risk-budget optimizer. It compares educational examples under shared
cash flows and market paths. A loss-comfort amount flags outcomes; it does not
select an investment, cap losses or establish suitability.

## What the first version missed

A small opening balance plus regular deposits produces a rising staircase even
in a losing market. Showing that balance alone makes the investment effect hard
to see. v0.4 displays net dollar P&L, unitized cumulative returns, percentage
return drawdown, cash-flow-weighted returns and a complete dollar reconciliation.
The animation switches between investment P&L, investment return and balance,
with a separate drawdown curve and a cash reference. Its initial view shows the
complete path; replay, pause, reset and a keyboard timeline remain available.

For a purely hypothetical $200 initial pot + $200/month, the more-cash example
in the 2022 replay ends at about $2,576.70 after $2,600 of deposits. Its net loss
is $23.30, cumulative unitized return about −4.14%, and return drawdown about
6.52%. The balance rises substantially because of saving; that is not investment
performance. This example is an accounting illustration, not the user's budget.

## Budget, fees and performance accounting

Protected reserve and near-term spending stay outside this pot and its goal.
A reserve shortfall absorbs monthly saving before investing. Deposits are fixed
nominal dollars. New contributions go proportionally toward positive dollar
shortfalls; the monthly 5pp band option resets with one fee-aware set of net
trades. This allocation rule differs from the research lab's L2 projection.

At each mark:

```
ending wealth = prior wealth + external deposit + market P&L − trading fees
pre-flow NAV = marked wealth / outstanding units
new units = external deposit / pre-flow NAV
post-trade NAV = ending wealth / all units
```

Fees are charged to old and new capital proportionally. Initial purchase costs
are included. A previously empty account starts at unit value one when first
funded; earlier returns remain missing, rather than being reported as zero.
NAV and its drawdown are invariant to scaling all dollar inputs together.
Small dollar amounts do not justify hiding a mathematically valid percentage;
the page puts those percentages next to dollars rather than prescribing a
minimum balance threshold.

Dollar dip uses a deposit-adjusted high-water mark. Percentage drawdown uses a
unitized-return high-water mark. These measure different things. Cumulative TWR
excludes cash flows; XIRR includes their timing. The UI converts XIRR to the same
total replay duration before comparing rates. No annual rate is placed next to
an unlabeled cumulative one. An annualized XIRR is retained only as an explicitly
named audit column. Streams without a timed investment have no XIRR.

## Daily scenario engine and model dependence

The four-asset performance cache contains SPY / GLD / IEF / BIL over the common
2007-05-30–2025-12-31 daily interval, with 223 full return months. The downloader
and hashed files remain local. A clean checkout uses a conspicuously synthetic
market and designed monthly stress; it does not pretend to show real history.

Joint contiguous 3/6/12-month blocks are sampled without wrapping across the end
of the data. Each selected month retains all observed daily returns and their
cross-asset order; different months retain their actual session counts. Holdings
are marked daily and contributions/trades occur at the month end. All candidate
allocations share exactly the same selected months within a case. The first
path from a fixed seed is used for playback, rather than a selected winner.

The BIL daily log-return sequence is shifted by a constant within each sampled
month so its monthly compound return equals the future cash assumption. Apply
the same shift to risky returns, preserving daily shapes and monthly excess log
returns. This is a constant-premium scenario construction, not a yield-curve or
bond-price forecast. The default cash assumption matches sample BIL geometric
monthly growth; inflation is an editable 2.5% assumption, not observed CPI.
BIL is a Treasury ETF proxy net of fund expenses, not an insured deposit account.

Purchasing-power views discount each contribution and fee at its own payment
date, rather than discounting all past deposits at the ending date. Real P&L
includes inflation erosion; return percentages remain explicitly nominal.

Three explicit assumptions use common month selections:

1. Sample historical excess log returns.
2. Those excess returns reduced by 2 log percentage points per year.
3. Zero expected excess log returns under the selected block sampler.

Non-wrapping blocks sample boundary months less often. For zero-premium
centering, at block offset j the eligible source months j ... j+N−block have
equal probability; subtract their per-asset mean excess log return. Expected
excess log return is then zero at every position and horizon prefixes remain
stable. The realized finite Monte Carlo sample is not forcibly re-centered.
Zero excess **log** return does not mean zero arithmetic return or guaranteed
wealth preservation. Trading costs and return dispersion still matter.

The page compares all three assumptions, and a six-cell grid of block length
× full/last-ten-years input. The allocation is fixed within that sensitivity
check. These are conditional model comparisons, not probabilities of the future.
Repeated simulations add no independent historical crises. Gold/equity sample
performance need not represent future premia. No unseen crisis, intraday low,
structural break or joint coverage guarantee is manufactured by resampling.

## A solved risk-balanced candidate and a matched control

Users explicitly choose the cash fraction. The remaining SPY/GLD/IEF slice is
allocated by solving a convex equal-risk-contribution problem. With positive
positions x and strictly PD covariance Sigma:

```
minimize 0.5 x' Sigma x − (1/3) sum(log(x_i)), x > 0
risky weights = x / sum(x)
variance share_i = weight_i (Sigma weight)_i / (weight' Sigma weight)
```

Daily simple-return covariance is annualized by 252, and 25% shrunk toward a
positive diagonal. Clarabel solves a scaled equivalent objective. The code
verifies positive definiteness, first-order residual and three equal variance
contributions; it does not silently substitute a different allocation on failure.
Cash share is a user constraint, not a risk-profile recommendation. Equal
estimated variance contributions are not equal dollar weights, equal crash
losses or a claim to maximize expected wealth.

The matching control always has the **same cash fraction** and equal risky
dollar weights. The cash-share/estimated-volatility curve varies only exposure
around the fixed risky mix; it is not an expected-return efficient frontier.
Cash is constant in that volatility estimate, while observed BIL can fluctuate
in historical replay. Risk estimates and correlations can fail in a crisis.

Covariance uses longer SPY/GLD/IEF history from the same verified raw snapshots,
without requiring BIL before its inception. At default lookback, each 2008–09,
2020 and 2022 event uses 756 observations ending strictly before replay starts;
the fitted event target stays fixed during that replay. Future scenarios use
information through the cached end date, 2025-12-31. Those fit dates overlap
historical resampling inputs: the future scenario comparison is exploratory,
not held-out evidence. Historical what-ifs are not a prospective strategy record.

## Verification, artifacts and remaining limits

[Derived v0.4 audit](../results/planner_v4/README.md) publishes 18 future cases,
six sensitivity cases and 18 historical replays for a made-up student budget.
It records causal fit dates, equal-risk shares, first-order error, dollar
reconciliation, source hashes and table hashes. No provider prices are included.
`PYTHONPATH=src python scripts/export_planner_audit.py` reproduces the export and
refuses to overwrite an existing output folder.

Tests independently reconstruct unit issuance, compare daily/monthly endpoints,
verify per-asset P&L plus fees, probe empty and small accounts, cross-check XIRR
against an annuity, exhaust all eligible zero-premium block positions, compare
ERC with SciPy, and contaminate future prices to check causal estimates. AI-assisted
Claude reviews identified sampler boundary bias, mixed rate periods, missing
same-cash controls and truncated covariance history; these were corrected.
Original v0.2 numeric-module and public-result hashes still verify.

ML remains in the research workspace; one-day ridge volatility estimates do not
produce multi-year expected returns or select an investment. The earlier
negative ML result remains visible. No whole-share orders, tax lots, broker
fills or intraday liquidity are modeled. The local Streamlit session receives
budget entries; there is no brokerage connection, saved financial profile or
budget telemetry. Downloading a JSON summary is explicit and includes the
entered budget; no entered budgets are published to GitHub.

Methods: [CVX risk-budget allocation exercise](https://www.cvxgrp.org/cvx_short_course/docs/exercises/notebooks/13.20.html),
[CVX portfolio optimization](https://www.cvxgrp.org/cvx_short_course/docs/applications/notebooks/portfolio_optimization.html),
and [Boyd et al., multi-period convex trading](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html).
These sources motivate objectives and constraints; this planner does not claim
to reproduce those papers or discover a new allocation method.
