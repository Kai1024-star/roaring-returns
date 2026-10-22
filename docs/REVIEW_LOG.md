# AI-assisted review and dispositions — 2026-10-22

Claude read `engine.py`, `policies.py`, `data.py`, `experiments.py` and the test
file in the desktop session. It reran the then-existing 16 tests read-only and
used scratch probes on the development outputs. Codex implemented changes; the
subsequent 21-test suite is separately run by Codex.

1. **Lagged minimum-sale fills may violate the planned band.** Confirmed. This
   was already a stated model limit, but the first report did not expose it
   sufficiently. The signal-price plan is retained without a hindsight-selected
   buffer. Event outputs now report actual post-trade deviation and compliance.
   There is no claim that the static theorem guarantees delayed execution.
2. **A single-width scatter is not an efficient frontier.** Accepted. Added the
   2/5/10pp sensitivity cases proposed in the earlier design, and common-date
   signal/post-trade RMS metrics. Daily outside-band frequency is retained as a
   secondary exposure measure. Cost-stress arguments and report headings now
   use the actual configuration rather than dataclass defaults/hardcoded labels.
3. **Missing calibration variables and ambiguous C/W denominator.** Fixed.
   Events distinguish signal wealth from execution pre-flow wealth, record both
   contribution ratios, the signal-state external cash needed for exact
   restoration (accounting for existing cash), reachability, and planned/actual
   trades for each asset.
4. **The first no-lookahead test compared only three aggregate quantities.**
   Strengthened with a multi-month path, changed future prices, and comparisons
   of all daily states before the cutoff and every asset's already-decided
   orders across all five rules.
5. **Corporate-action consistency checks were not persistent, and unmatched
   action dates were skipped.** Internal audits and maximum discrepancies are
   stored in the data manifest; unmatched events now fail. Two distinct return
   conventions are compared, with documented sanity tolerances.

Claude agreed that TWR and initial investment-cost treatment match the unit
issuance convention implemented in the engine. It also found no error in the
analytic allocation decomposition. Additional independent QP checks have since
been added to validate the target-distance tie-break and buy-only projection.

Important source distinction: the review's reference to a “CRSP-style” formula
does **not** mean CRSP data were acquired or used for independent validation.
Both internal return checks use the same Yahoo snapshot. External-provider
certification, pay-date income, whole shares, and taxes remain outside v0.1.

The untraded zero-contribution proportional and buy-only cases coincide. They
are transparent duplicate controls, not independent market observations.

## Publication review and later-period runs

Claude reported no blocking implementation issue, reran the 21 tests read-only,
and checked split anchors. Codex then completed validation and evaluation with
the same baseline source hashes, data hash and parameters as development.
Claude's smoke checks ran in memory without reporting or examining outcome
metrics; this does not turn publicly known history into a prospective test.

Public documentation now identifies the review as AI-assisted, explains the
unused bootstrap seed, the descriptive validation segment, cost units, cash-flow
neutral TWR and the lack of money-weighted returns. Aggregate results and
relative links are exported to results/; detailed local ledgers stay excluded.
The initial protocol and source hashes preserve the pre-Git experimental state.
Output overwrite protection, a zero-selling nan display edge case, bootstrap
inference, and a newer-data snapshot remain engineering/research follow-ups.

## Final cross-period result review

Claude recomputed the public tables, manifest hashes, and selling-month band
violations from local outputs. All numerical checks agreed. The publication
now adds (1) cash-flow-intensity and carried-state reachability summaries,
(2) counts and overshoot magnitudes alongside violation rates, and (3) the
2pp minimum-sale versus 5pp center-reset comparison, including selling frequency.
It also discloses duplicate 10pp outcomes and post-generation prose/link edits.
A new contribution map uses the primary common-signal RMS metric; the original
daily band-exposure maps remain clearly secondary. No policy, target, band,
source numerical module, or data snapshot changed in this presentation update.

## v0.2 execution-risk extension, 2026-10-22

The user authorized a personal Python research upgrade and a showcase demo.
Codex implemented the new modules and inspected author source files; Claude
reviewed relevant full-paper sections, the implementation and numerical probes.
This is AI-assisted engineering review, not human peer review or a reproduction
of the cited papers. Six pinned author-source files were inspected read-only;
none of the external training/backtest pipelines were executed.

The first tracking-QP study greatly reduced drift by selling far more. Its
forecast variants were nearly identical. In response, an analytic lag buffer
and a separate risk-budget minimum-sale objective were added as explicit
comparators. This was exploratory method development after seeing the first
QP outcomes, not a prospective preregistration. No historical parameter grid
search was performed. Existing 2005–2025 outcomes were already known.

Claude identified the following problems, which were corrected or disclosed:

1. A soft tracking penalty does not recover a static minimum-sale objective.
   We retain the tracking QP as a separate ablation and test the new sales
   program's hard-zero-risk/zero-cost/zero-shock limit.
2. Under frozen dollar fills, next-day returns act on original holdings. The
   analytic Jacobian uses H/S; it does not substitute post-trade target weights.
3. Subsampling 64 historical observations and mixing designed shocks created
   avoidable scenario sensitivity. Final runs use all up to 252 causal,
   individually filtered historical residuals. Designed stress is separate.
4. Ridge clipping, mature label dates, a common warm-up, tail activity,
   fill adjustments and solver statuses are explicitly recorded. The first
   ETF account is initialized 2005-12-30, yielding 108 monthly fills; the
   requested-window label is not a full January-2005 start.
5. Tight tie-break constraints exposed numerical failures. The same QP retries
   through OSQP, then preserves a verified first-stage LP solution if necessary.
   ETF runs have 28 retries and zero LP-only months; synthetic runs have 22
   retries and two LP-only months, whose nearest-target tie-break is incomplete.
6. The tracking tie-break initially spent its numerical tolerance on cent-level
   sales, inflating selling counts. Zero-sale optimal faces are now strictly
   buy-only; nonzero faces cap sales/slack separately. Exact buy-only funding,
   independent HiGHS CVaR epigraph checks and the Jensen mechanism are tested.

The final numerical code/configuration is identical across the 36 ETF and 36
synthetic configurations; the data sources differ. Forty local tests passed,
including a browser-independent Streamlit integration check, future-data
poisoning, fees/flow neutrality, old-ledger equivalence at the same configuration,
LP/QP cross-checks and explicit tie-break-failure disclosure. Browser checks
also verified that future shock controls change outcomes without changing
frozen order IDs. CI installs the solver/demo extras so these checks are enabled.

The public result interpretation preserves a negative ML finding: ridge QLIKE
is worse than EWMA in all three ETF periods. Risk-budget execution reduces
observed violations while generally selling more; the analytic buffer is a
strong simple comparator. Conditional monthly block intervals are not an
untouched holdout, model-refit bootstrap, or a claim of superiority. Papers,
raw provider data, original author code and private daily ledgers are excluded
from publication; original code, provenance and derived aggregates are included.

After the final numerical runs, presentation-only updates added explicit model
scores and solver counts to REPORT, and a uniform material-sale reporting
threshold of 1e-6 of signal wealth. The original summary's legacy >1e-7 USD
count remains available. This removes residual tracking-QP rounding effects
from displayed selling frequency without modifying any trade or path. A separate
presentation manifest records the renderer; numerical source and outcome hashes
are still checked. ETF and synthetic first windows have 108 and 120 monthly
fills respectively because their available prehistory differs; they are separate
mechanism studies, not paired market observations.

## v0.3 beginner budget homepage, 2026-10-22

The user requested an English, approachable main page for small budgets while
retaining the optimization/ML research workspace. Claude first reviewed the
product scope, then ran read-only implementation/accounting probes. The page
uses fixed examples, never maps loss tolerance to a recommended portfolio, and
keeps one-day ML estimates out of multi-year scenario generation.

The first review found that a 2pp haircut to historical total returns combined
with an unrelated 3% cash assumption disadvantaged the Treasury-fund example.
It also found that monthly stress understated within-month losses. We added a
separate SPY/GLD/IEF/BIL snapshot, rebased future returns on historical BIL excess
log returns, and implemented daily-close historical replay with monthly funding
and fee-aware net trading. The initial default cash assumption is now the BIL
snapshot's geometric annualized monthly mean (1.3043% in this snapshot), with
zero default premium reduction. Changing that rate shifts all future asset log
returns equally under the explicitly stated constant-premium assumption. It is
not a current deposit quote or a yield-curve forecast. Historical replay cash
uses actual observed BIL returns, independently of future cash settings.

The same review led to a savings-reference default, made-up sample-budget labels,
explicit 7–10 year Treasury-fund interest-rate risk, nominal ending-loss labels,
and month-end future-dip labels. Technical resampling/interest assumptions are
available behind an expander; the main flow focuses on dollars, stress and choices.
Claude's final focused probes confirmed the cash baseline and BIL replay behavior,
and found no remaining blocking numerical issue. This is AI-assisted engineering
review, not professional financial advice or human peer review.

59 local tests passed, including clean-checkout synthetic fallback, Streamlit
navigation/budget submissions, reserve-gap funding, cash-anchor equivalence,
population log-mean preservation, daily/month-end fee reconciliation, recovered
intramonth crashes, monthly-only contributions, and future-price contamination.
The existing checker still verifies all 7 v0.2 numerical modules and both public
36-case result sets; original trades and research outcomes were not changed.
Browser checks cover sample-budget selection, an unfunded-reserve case, scenario
units, dated replay/pause/reset and keyboard navigation. Raw prices, PDFs and
entered budgets are excluded from the GitHub release.

## v0.4 performance, scenario and optimization upgrade, 2026-10-22

The user correctly challenged a deposit-dominated account-balance animation.
A hypothetical $200 initial investment plus $200 monthly in the More cash
example ends the 2022 replay near $2,576.70 after $2,600 of deposits: net
investment P&L is -$23.30, despite the rising staircase. This is a made-up
accounting example, not an observation about the user's finances.

The default animated measure is now net investment P&L, with separate account
balance and unitized return views, a cash reference, exact fee/asset attribution,
and a return-drawdown panel. Unit issuance separates external contributions
from performance; money-weighted return is converted to the same replay period
before display beside cumulative time-weighted return. Unfunded performance
is missing rather than a fabricated zero return. Purchasing-power views discount
each deposit and fee at its own payment date. Real P&L includes inflation erosion;
return percentages remain nominal.

The future engine now samples non-wrapping joint whole-month blocks while
retaining every observed daily return within each month. It values holdings
daily and funds/trades at month ends. All allocations share month selections.
Three explicit excess-log-return assumptions and a 3/6/12-month by two-window
sensitivity grid expose dependence on the model. The zero-premium assumption
uses the eligible-month mean at each block offset, accounting for the unequal
sampling of boundary months; it does not recenter realized simulation draws.

A convex log-barrier risk-budgeting solve provides a genuine equal-variance-
contribution candidate, with user-selected cash, shrunk covariance, positive-
definiteness/first-order audits and a same-cash/equal-risky-weight comparator.
Historical replay fits only pre-event prices. Separately hash-verified risky
asset history avoids shortening the 2008 covariance window to BIL's inception.
The optimizer is not a return forecast, suitability assessment, or new algorithm.
The original execution-risk ML experiment, including its negative ridge result,
remains available in Research lab without changes to its numerical modules.

Claude performed read-only AI-assisted method and implementation reviews. Four
substantive findings were corrected: sampler-weighted zero-premium centering,
comparable return-period labels, the matched cash control, and pre-2008 risky
history. A final focused review confirmed cash-flow-date discounting (cash equal
to inflation reconciles to zero real P&L at monthly endpoints) and daily animation
drawdown consistency. Aggregated future arrays store month-end drawdown snapshots;
their scalar maximum drawdown uses daily observations. Daily animations receive
the separate full daily sample path, not those month-end snapshots.

73 local tests passed. They cover accounting, daily/monthly reconciliation,
unfunded states, purchasing power, capital scaling, non-wrapping/prefix-stable
sampling, conditional zero-premium centering, SciPy cross-solves of risk budgeting,
future-price contamination, Streamlit integration and the earlier research tests.
The offline planner checker verifies 4 numerical source hashes and 42 derived
demonstration cases (18 future comparisons, 6 sensitivities, 18 historical replays),
including 3 causal fits and dollar reconciliation within $1e-8. The original
7-module/72-case execution export audit still passes.

Browser checks verified actual fan and drawdown charts, allocation/covariance
controls, model/input-window changes, all three animation measures, replay,
reset and keyboard stepping. Display screenshots use a made-up sample budget.
Only original code, documentation, aggregate demo audits and these screenshots
are published. Provider snapshots, paper PDFs, budgets and local environments
remain excluded. The scenarios are exploratory conditional illustrations; no
untouched holdout, future probability calibration or superiority claim is made.

## v0.5 multi-asset ensembles and representative scenarios, 2026-10-22

The user requested realistic market inputs, many visible branching paths, and
an explanation of which scenario patterns the model regards as more common.
A new English Market simulator workspace is the default entry point. Prior
budget and execution workspaces remain available without changing their numeric
source hashes or published outcomes.

An independently versioned local Yahoo snapshot contains 13 ETF proxies through
2026-10-22, with 4,842 common sessions from 2007-07-26. Actual quote/reference
levels are separated from adjusted-close return proxies. Oil exposure is USO,
a futures fund with roll/structure risk, not spot crude. Raw and processed
hashes, splits, positive prices, same-provider return conventions and common
calendars are checked. Updates are explicit; old snapshots are not overwritten.
There has been no second-provider or CRSP validation of these new inputs.

The default generator uses joint non-wrapping daily blocks, with exact
conditional centering at each block offset. Correlated GBM is an explicit
normal-log-shock comparator. Both use the same stated cash anchor and retained
historical excess log drift. Daily unitized NAV, cash flows, fees, drawdowns
and arbitrary-N account conservation reuse the earlier net-trade conventions.
Model months have 21 sessions, not literal future holiday calendars.

Claude performed AI-assisted read-only design and numerical reviews. The first
implementation review identified covariance regularization that suppressed
observed equity correlations, random-window sensitivity in the CVaR optimizer,
and unstable single-start shape grouping. Corrections made before publication:

1. Default covariance is observed completed-week sample covariance, with only
   a minimal eigenvalue floor if needed; raw and model correlations are shown.
   On the reviewed full core sample, the floor did not bind and covariance
   differs from raw only at floating-point precision.
2. Downside allocation now solves CVaR over all overlapping 21-session historical
   windows, not a random subset of 1,000. With 4,821 windows, 5% tail mass is
   241.05 observations; the fractional boundary is included in the objective
   audit. Overlapping windows are explicitly not independent observations.
3. Descriptive grouping uses five equally spaced horizon fractions of log NAV
   plus maximum drawdown, 12 fixed initializations and minimum inertia. Group
   representatives are actual group members nearest their feature center.
   Shares are rounded, and the UI explains dependence on grouping and simulation
   batch. Changing random batches can shift shares by several percentage points.

Claude's focused recheck found these corrections sound and no new substantive
numerical error. An earlier observation about absent tests was made while the
new test file was being added; the final suite contains 87 passing tests.
These include GBM moment/correlation checks, cash annuity and unitization,
prefix consistency, exact block/window centering, future-data poisoning,
arbitrary-N ledger and scale invariance, snapshot corruption, fractional CVaR,
HiGHS LP and SciPy QP cross-solves, group membership/determinism and four-view
Streamlit integration with GBM, fresh batches and advanced USO inspection.

The public export contains 32 conditional model cases and 128 scenario-group
rows for a made-up $1,000 initial + $100/month account. Source/artifact hashes,
allocation caps, group partitions and dollar conservation are verified offline;
maximum observed dollar reconciliation error is below $1e-8. The old 42-case
planner audit and both 36-case execution exports still pass.

The largest descriptive group is not promoted to a posterior probability or a
uniquely most-likely future trajectory. The minimum-variance and one-month CVaR
objectives consider risk across outcomes under explicit exposure constraints.
They do not optimize a predicted multi-year path or establish a suitable
investment. Different generators and random seeds add no independent historical
evidence, and the full historical window has already been examined.

Live browser checks verified the multi-path canvas, representative-group changes,
GBM switching, P&L/return views, animation/pause/reset/keyboard stepping, observed
stock/gold/oil/Treasury curves, and the final optimizer page. Integration tests
also verify fresh random batches, USO inspection and budget retention across all
four views. Public preview images use the made-up default account.
