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
