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
