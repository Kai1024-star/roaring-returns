# Execution-risk optimization, v0.2

This personal research extension asks how a fixed-target, contribution-aware
portfolio should plan trades when prices change between the signal and fill.
It preserves the v0.1 ledger and results. It adds finite-scenario optimization,
causal risk forecasts, matched controls, diagnostics and a local interactive app.
It is an application of existing methods, with no novelty or alpha claim.

## Decision and funding contract

At the signal close observe invested dollars H, existing cash K and the next
contribution C. Freeze dollar purchases b and sales s. Original holdings earn
the next session's return r before the frozen trades fill at that session's close:

```
X(r) = H * (1+r) + b - s
(1+kappa) sum(b) = K + C + (1-kappa) sum(s)
W(r) = sum(X(r))
S = sum(H) + K + C
```

The budget anticipates proportional fees on both purchases and sales.
Scenario sale caps and long-only constraints prevent planned scenario shorts.
Outside sampled scenarios, the common fill engine caps sales and scales buys;
the realized adjustment is recorded. These are return-unit proxies, not live
share orders. No brokerage connection or live execution exists.

For target a and absolute band k, define loss for scenario j as
`ell[j] = max(0, max_i(abs(X[j,i]-a[i]*W[j])-k*W[j])) / S`.
The denominator S is fixed at decision time: this keeps the optimization convex.
This loss is normalized dollar band excess, not exact weight-percentage CVaR.

## Two distinct optimization objectives

**Tracking QP:** minimize mean squared normalized dollar tracking error, plus
0.002 times gross turnover/S, plus 0.5 times empirical 90% CVaR of ell.
This method can trade toward the center every month and sell much more. It is
an explicit comparator, not a minimum-sale policy.

**Risk-budget sales LP, followed by a QP:** minimize
`sum(s)/S + 50 * epsilon`, with empirical CVaR at most `0.0005 + epsilon`.
Epsilon is nonnegative and reported. A 0.0001 reduction in excess risk budget
is valued like 0.005 of capital in sales; this is a scenario preference, not an
estimated investor utility. This is a soft risk budget, not a guarantee.
The second stage minimizes tracking error within 1e-6 of the normalized first
objective. The tolerance is numerical, so exact lexicographic optimality is not
claimed. Sales and slack are also capped separately at the first-stage values
(1e-9/1e-10 normalized roundoff); if the primary optimum is below 1e-8, the
second stage imposes zero sales and zero slack. Buy-only roundoff is re-funded
exactly on that face. Tracking cannot spend 1e-6 of capital on micro-sales merely
to improve tracking or inflate the count of selling months.
Zero shocks, zero costs and a hard zero risk budget recover the static
minimum-sale rule; the soft default does not have that identity.

Both solve with open-source Clarabel through CVXPY. For the sales variant, a
failed second-stage QP retries the same program with OSQP. If that also fails,
the saved optimal LP solution is used only after verifying funding, long-only
scenario holdings, risk and the primary objective. Status `optimal_lp_only` and
`tie_break_incomplete_months` disclose that the nearest-target selection was not
completed. First-stage/feasibility failure aborts the run and writes a failure
record. No alternate trading rule is silently substituted.

## Forecasts, scenarios and analytic comparator

Three covariance alternatives are compared: equally weighted historical,
shrunk EWMA (21-session half-life), and ridge next-session variance. Ridge uses
log realized variance over 1, 5 and 22 sessions; standardized features use only
the mature training window, and X[t] is paired with the observed r[t+1]^2.
The current feature vector has no training label. Up to 504 mature labels are
used, with minimum 126, penalty 10 and an unpenalized intercept. Negative/extreme
predictions are clipped to 0.1–10 times the EWMA variance; clip counts and any
EWMA fallback are visible. Correlations remain shrunk EWMA. This is transparent
risk estimation, not expected-return prediction or decision-focused learning.

Each historical return is standardized using an EWMA estimate formed before
that return. The most recent up to 252 joint residuals are centered and recolored
using the current covariance. The default uses all available residuals, without
random subsampling or equal-probability artificial stress shocks. Return shocks
are clipped to [-50%, 50%], a declared numerical/stress limit. Empirical CVaR
levels do not imply calibrated future probabilities or distributional coverage.
Designed shocks are separate what-if inputs in the app.

The analytic buffer uses the correct frozen-dollar Jacobian:
`J = diag(H/S) - a (H/S)^T`.
Per-asset buffer `1.65 sqrt(diag(J Sigma J^T))`, capped at 80% of the band,
tightens the static minimum-sale bands. This inexpensive strong comparator
has no joint 95% coverage guarantee.

For exactly centered, unclipped scenarios, convexity also implies the zero-shock
dollar band excess is at most mean scenario loss, hence at most CVaR. This is a
one-session property under these assumptions; it does not bound drift over the
following month or survive arbitrary changes to the scenario distribution.

## Experiment and interpretation

`configs/execution_v2.json` fixes twelve methods across three retrospective
windows: 36 configurations on cached ETF history, and 36 on separate artificial
regime-switching Student-t paths. Same target, funding, fees and decision times
are used by every method. A common 252-session pre-decision warm-up applies;
the first ETF window therefore starts later than the requested January 2005.
Realized dates are recorded, not concealed by window labels.

Report post-fill RMS, violation counts and overshoot magnitudes alongside
selling amount, selling frequency, fees and fill adjustments. Risk scores use
the actual next execution-session squared return (QLIKE); decision outcomes
are a separate evaluation. Do not choose a model from the displayed result.
Analytic and ML risk models can lose to simpler controls.

Six-month circular-block resampling keeps paired monthly outcomes together.
The reported intervals are conditional descriptive summaries: models are not
refit and portfolio paths are not reconstructed. They assume useful temporal
stability and do not repair selection bias, prove superiority, or create an
untouched holdout. The 2005–2025 history was already inspected in v0.1.

All runs write unique directories, a protocol snapshot, source/data hashes,
solver diagnostics and environment versions. Public exports include only
derived aggregate reports and monthly portfolio metrics; raw provider data,
paper PDFs and full daily ledgers remain local. Original v0.1 results remain
separate because their baseline fees and experiment questions differ.

## What was learned from the papers and source code

The team examined relevant methods, derivations and experiment sections, not
every line of all fourteen papers. The implementation map records adoption
and non-adoption for each paper. Six original source files from three author
repositories were inspected read-only at pinned Git tree revisions; hashes and
URLs are in `reference_code_provenance.json`. Those experiments were not run,
and no third-party source has been incorporated into this package.

The direct implementation influence is self-financing convex construction
(Boyd 2017/2024), scenario tail-risk constraints, and the separation of forecast
accuracy from downstream decisions discussed in DFL research. We have not
reproduced differentiable layers, learned OT ambiguity geometry, multi-period
DFL, RL, quantum algorithms or pension liability models. The source list and
paper metadata are in `LITERATURE_REVIEW_2026-10-22.md`.

The current demo needs no external credentials. Columbia WRDS/CRSP would be
relevant to a separate stock-level reproduction, not this implementation.

## Demonstration

Install `.[demo,validation]` and run `python -m roaring_returns demo`.
The synthetic market works offline on a clean checkout. Published historical
aggregate results are viewable, while a cached-price signal lab requires the
local Yahoo snapshot. The four tabs expose frozen plans, realized shock
comparisons, historical tradeoffs, risk-model diagnostics, and provenance.
Changing a future shock changes outcomes without changing the order ID.

Next steps require a new protocol: prospective shadow tracking, covariance
calibration, nested path-level inference, multi-period cash contributions, and
only then end-to-end learned risk preferences if justified by evidence.
