# Multi-asset market simulator v0.5

This English workspace expands Roaring Returns from a single replay and
percentile summary to inspectable daily path ensembles, descriptive scenario
groups, observed market data and constrained allocation. It is an educational
research implementation, with no claim of calibrated future probabilities,
alpha, suitability, novelty or an untouched holdout.

## What is observed

A separate immutable snapshot requested through 2026-10-22 contains 13 ETFs:
US equity styles (SPY/QQQ/IWM), ex-US stocks (VEA/VWO), gold/silver funds
(GLD/SLV), an oil-futures fund (USO), Treasury exposures (SHY/IEF/TLT/TIP),
and the BIL cash proxy. The common calendar starts 2007-07-26 and has 4,842
sessions. Per-fund downloads retain their earlier available histories, but the
multi-asset estimator deliberately uses complete common observations. There
are more assets, not thousands of new independent crises.

Historical vendor Close is **split adjusted**, not an original executable
historical price. Adjusted-close ratios are total-return proxies with implicit
distribution reinvestment; fund expenses are embedded, not charged again.
There are same-provider return/split/positive-price/calendar checks, with raw
and processed SHA-256 checks on load. This is not independent-provider validation.
USO's futures rolls, changing exposures and expenses differ from spot crude.
See [USCF disclosures](https://www.uscfinvestments.com/disclosures).

Fetching is explicit (`fetch-market --cutoff YYYY-MM-DD`); existing dated
snapshots are reused without silently overwriting prior versions. No raw provider
series, user budget, credentials or paper PDF enters the public export. A clean
checkout uses labeled synthetic data until a snapshot is fetched.

## Two conditional generators

Calibration uses only the requested window at or before the as-of date. Future
cash log growth is an editable assumption, common to all assets. The risky
asset log drift is cash log growth plus a retained fraction (default 25%) of
its historical excess log mean. Zero retained premium means zero expected
**excess log return**, not zero arithmetic excess return. A bond fund can have
negative retained premium in a particular window; this is an inherited scenario
assumption, not a prediction that it must lose to cash.

1. **Joint historical blocks**, default: sample complete non-wrapping daily
   vectors in 5/21/63-session blocks, preserving cross-asset alignment and some
   serial dependence. Each eligible block-offset population is centered before
   adding the target log drift. Boundary dates have unequal sampling frequency,
   but the expected log drift is exact at each position. Prefixes are stable
   when only horizon changes. No unseen crisis is manufactured.
2. **Correlated GBM**: draw normal log shocks with annual covariance estimated
   from completed weekly returns. The implementation uses log drift directly:
   `log(S[t+dt]/S[t]) = m*dt + L*sqrt(dt)*Z`. Its arithmetic SDE drift is
   `m + diag(Sigma)/2`; there is no second half-variance subtraction. GBM has
   constant covariance, thin normal log tails and no volatility clustering.

Weekly covariance uses the observed sample covariance, with only an eigenvalue
floor `max(largest_eigenvalue*1e-6, 1e-10)` for numerical conditioning. The
default performs **no 25% diagonal shrinkage**. Raw and model correlations are
displayed so a regularizer cannot masquerade as observed diversification.
Weekly sampling can reduce timing effects, not guarantee their removal. It is
not identical to the daily-block covariance; model differences have several
causes, not just tail thickness.

## From many paths to representative scenarios

Every simulation has a fixed ID. Thin displayed trajectories start with the
same ID prefix, without choosing high-return winners. P5/P50/P95 summarize all
paths pointwise; none is itself necessarily a real path. Additional bold curves
are actual simulated representatives of descriptive shape groups.

Features are log NAV at 20/40/60/80/100% of the horizon and maximum daily
drawdown, standardized across the ensemble. Four-group k-means uses 12 fixed
initializations, choosing the lowest-inertia nonempty partition. Each group's
representative is its actual member nearest its feature center. Group counts
sum to the path count; reported shares are rounded. The largest group is
highlighted initially.

Changing features, group count, horizon, calibration or the generator can change
the partition and its largest group. These shares are **not posterior weights,
probabilities of exact continuous paths, or calibrated real-world odds**. The
purpose is to inspect common and adverse patterns without promoting a selected
random line as the uniquely most-likely forecast.

## Optimization across outcomes

Cash is fixed by the user; other constraints are long-only, sum-to-one, a minimum
equity exposure, a maximum individual risky-fund weight, a combined commodity
cap and a separate 10% USO cap. Defaults are illustrative, not personal advice.
The UI reports infeasibility and identifies binding minimum-variance constraints.

- Minimum variance minimizes `w_risk' Sigma w_risk`, with no maximized expected
  return. The displayed equity-exposure/risk curve holds cash fixed; it is not
  a return-efficient frontier. Different estimation windows expose sensitivity.
- Scenario downside allocation minimizes Rockafellar–Uryasev 95% CVaR of gross
  one-month portfolio loss. It uses **all overlapping 21-session historical
  windows**, centered as a complete population and shifted to the stated cash
  and log-growth assumptions. There is no random training-window seed. Exact
  fractional boundary mass is included in the empirical tail-objective audit.
- The control projects equal risky-capital weights onto the identical feasible
  set. The separate fixed class example need not satisfy arbitrary user caps.

The downside optimizer always fits these historical one-month windows, regardless
of the generator used to evaluate multi-year paths. Those windows overlap and
are not independent observations. Its one-month gross objective is not a
multi-year maximum-drawdown guarantee or an optimization of the trading policy.
Future simulations use the same underlying historical information and provide
conditional model checking, not independent evidence of superiority.

The CVaR formulation is described in [CVX risk models](https://www.cvxgrp.org/cvxrisk/models/).
The implementation is original and simplified; no claim is made to reproduce
that library or [multi-period convex trading](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html).

## Ledger, display and tests

Each modeled month has 21 daily sessions, with 252 per year. This is trading
time, not a literal future holiday calendar. Contributions arrive after the
month's return; net rebalancing then prioritizes additions and restores a 5pp
band if necessary. Fees follow the v0.4 self-financing net-trade equation.
Unit issuance separates deposits from returns; initial and later fees are in
performance. Dollars are nominal in this workspace. Protected money must be
excluded from the investable-now input; the budget planner offers that workflow.

The engine checks ending wealth = deposits + market P&L − fees for every path.
It tracks all daily NAVs and drawdowns, including initial purchase fees. Unfunded
periods have missing returns. Inputs and account paths are in session memory;
only market data is globally cached. JSON reports are local downloads.

Tests include GBM moments/correlation, shared cash growth, deterministic block
centering and prefix consistency, future-data poisoning, arbitrary-N accounting,
capital scaling, funding dates, fractional CVaR, independent HiGHS CVaR and SciPy
minimum-variance solves, scenario partition/membership, source hash corruption,
and clean-checkout UI interaction. The prior planner/research numeric files
and their published outcomes remain unchanged.

## Reading the comparison workspace

The Optimize view compares four objectives in a fixed order, without a winner
badge or ranking. Every candidate is evaluated using the same budget, seed,
asset-return draws and monthly trading policy. P5/median/P95 are model-conditional
endpoint summaries after fees, displayed as either nominal balance or net P&L.
The balance axis zooms to the outcome range and is labeled accordingly.

The second interval chart first subtracts the same-constraint reference on
**each path ID**, then takes quantiles of those differences. It does not subtract
unpaired quantiles. Initial dollar holdings come from the fee-adjusted ledger;
initial fees are shown separately. The gross one-month fitted CVaR is scaled
only by the initial budget, excludes future deposits/fees, and is separate from
P95 multi-year daily return drawdown. With zero starting capital the fitted
CVaR is displayed as a percentage; unfunded return drawdown stays unavailable.

The cross-generator control offers an assumption check using GBM and joint
blocks. Both depend on the same historical calibration; the comparison is not
held-out validation. “Simulate this allocation” preserves budget, weights,
generator, seed and assumptions and restores portfolio inspection. Research
formulas, binding constraints and estimation sensitivity sit in collapsed
details. Window order is explicitly 3/5/10/20 years; all 13 funds have stable,
unique colors across observed-market and diagnostic charts.

The Budget planner historical replay now overlays up to four examples with
identical deposits and dates. The selected example remains bold and controls
the displayed holdings and ledger; comparison toggles do not silently change
it. Hover/date stepping updates the inspection values. Net P&L is the default,
negative-P&L shading means below cumulative deposits, and return drawdown is a
separate daily unitized-NAV chart. The cash proxy is not smoothed. These stress
periods were selected deliberately and do not represent typical markets.
