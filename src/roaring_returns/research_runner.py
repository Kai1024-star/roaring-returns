"""Reproducible retrospective v0.2 study and aggregate-only presentation export."""

from dataclasses import asdict, fields
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
from .data import load_prices, digest
from .execution_research import ResearchConfig, RESEARCH_STRATEGIES, LABELS, backtest_execution, research_summary
from .synthetic import synthetic_prices


def paired_intervals(reference, candidate, *, repetitions=1000, block=6, seed=20261022):
    """Conditional circular-block resampling of paired MONTHLY outcomes.

    This does not refit models or reconstruct portfolio paths. It is a descriptive
    stationarity-dependent interval, not new out-of-sample evidence or a full
    end-to-end inference procedure.
    """
    if (len(reference) != len(candidate) or len(reference) < 2
            or repetitions < 1 or block < 1):
        raise ValueError("Matched monthly events and positive bootstrap settings required.")
    if not np.array_equal(reference.execution_date.to_numpy(), candidate.execution_date.to_numpy()):
        raise ValueError("Paired inference requires identical execution dates.")
    n = len(reference)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, (repetitions, int(np.ceil(n/block))))
    indexes = ((starts[:, :, None]+np.arange(block)) % n).reshape(repetitions, -1)[:, :n]
    functions = {
        "posttrade_rms_difference_pp": ("posttrade_rms_deviation_pp", lambda x: np.sqrt(np.mean(x*x, axis=-1))),
        "violation_fraction_difference": ("posttrade_outside_band", lambda x: np.mean(x, axis=-1)),
        "annual_sales_signal_fraction_difference": ("actual_sales_fraction_signal", lambda x: 12*np.mean(x, axis=-1)),
    }
    rows = []
    for name, (column, function) in functions.items():
        r, c = reference[column].to_numpy(float), candidate[column].to_numpy(float)
        draws = function(c[indexes])-function(r[indexes])
        rows.append(dict(metric=name, difference=float(function(c)-function(r)),
                         lower=float(np.quantile(draws, .025)), upper=float(np.quantile(draws, .975)),
                         observations=n, repetitions=repetitions, block_months=block))
    return rows


def source_data(root, source):
    if source == "yahoo":
        prices, manifest = load_prices(root)
        return prices, {"source": "cached Yahoo adjusted-close return-unit proxy",
                        "data_sha256": manifest["processed_sha256"],
                        "source_manifest": manifest}
    if source == "synthetic":
        prices = synthetic_prices()
        encoded = prices.to_csv(float_format="%.12g").encode()
        return prices, {"source": "SYNTHETIC regime-switching Student-t paths; not market data",
                        "data_sha256": sha256(encoded).hexdigest(), "seed": 20261022}
    raise ValueError("Data source must be yahoo or synthetic.")


def run_study(root, *, source="yahoo", output=None, periods=None, progress=None):
    root = Path(root)
    config_path = root/"configs/execution_v2.json"
    protocol = json.loads(config_path.read_text())
    prices, data_metadata = source_data(root, source)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ")+"_"+digest(config_path)[:8]
    output = Path(output) if output is not None else root/"reports/v2"/run_id
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing research run: {output}")
    output.mkdir(parents=True)
    (output/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    allowed = {f.name for f in fields(ResearchConfig)}-{"strategy"}
    common = {k: v for k, v in protocol.items() if k in allowed}
    common["target"] = tuple(common["target"])
    windows = {k: v for k, v in protocol["retrospective_windows"].items() if periods is None or k in periods}
    if not windows:
        raise ValueError("No requested research periods found.")
    summaries, monthly, curves, intervals, diagnostics, failures = [], [], [], [], [], []
    for period, (start, end) in windows.items():
        results = {}
        for strategy in protocol["strategies"]:
            if strategy not in RESEARCH_STRATEGIES:
                raise ValueError(f"Unknown strategy {strategy}")
            if progress:
                progress(f"{period}: {LABELS[strategy]}")
            config = ResearchConfig(strategy, **common)
            try:
                result = backtest_execution(prices, config, start=start, end=end)
            except Exception as error:
                failures.append(dict(period=period, strategy=strategy, error=str(error)))
                # A failed optimizer is never replaced by another strategy.
                (output/"failures.json").write_text(json.dumps(failures, indent=2)+"\n")
                raise
            results[strategy] = result
            result.daily.to_csv(output/f"daily_{period}_{strategy}.csv.gz", compression="gzip")
            result.events.to_csv(output/f"events_{period}_{strategy}.csv", index=False)
            row = dict(period=period, strategy=strategy, label=LABELS[strategy], **research_summary(result))
            row["violating_months"] = int(result.events.posttrade_outside_band.sum())
            row["violating_selling_months"] = int(result.events.loc[result.events.actual_sales > 1e-7, "posttrade_outside_band"].sum())
            row["ridge_fallback_months"] = int((result.events.used_model == "ewma_fallback").sum())
            summaries.append(row)
            cols = ["execution_date", "posttrade_rms_deviation_pp", "posttrade_max_deviation_pp",
                    "posttrade_excess_pp", "posttrade_outside_band", "actual_sales", "actual_buys", "fees",
                    "actual_sales_fraction_signal", "signal_rms_deviation_pp", "used_model", "training_samples"]
            small = result.events[cols].copy()
            small["period"], small["strategy"], small["label"] = period, strategy, LABELS[strategy]
            monthly.append(small)
            nav = result.daily[["nav", "rms_deviation_pp"]].resample("ME").last().reset_index()
            nav["period"], nav["strategy"], nav["label"] = period, strategy, LABELS[strategy]
            curves.append(nav)
        reference = results["min_sales_band"].events
        for strategy, result in results.items():
            if strategy != "min_sales_band":
                for row in paired_intervals(reference, result.events,
                        repetitions=protocol["paired_bootstrap_repetitions"],
                        block=protocol["paired_bootstrap_monthly_block"]):
                    intervals.append(dict(period=period, strategy=strategy, **row))
        model_events = results["scenario_ridge"].events
        for model in ("historical", "ewma", "ridge_vol"):
            diagnostics.append(dict(period=period, model=model, score="monthly execution-session variance QLIKE",
                mean_qlike=float(model_events[f"qlike_{model}"].mean()), observations=len(model_events),
                fallback_months=int((model_events.used_model == "ewma_fallback").sum()) if model == "ridge_vol" else 0,
                ridge_training_samples_mean=float(model_events.training_samples.mean()) if model == "ridge_vol" else 0))
    summary = pd.DataFrame(summaries)
    summary.to_csv(output/"summary.csv", index=False)
    pd.concat(monthly, ignore_index=True).to_csv(output/"monthly_metrics.csv", index=False)
    pd.concat(curves, ignore_index=True).to_csv(output/"monthly_curves.csv", index=False)
    pd.DataFrame(intervals).to_csv(output/"paired_intervals.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(output/"risk_diagnostics.csv", index=False)
    import cvxpy
    import clarabel
    numerical_modules = ("data.py", "policies.py", "engine.py", "risk.py", "optimization.py",
                         "execution_research.py", "synthetic.py")
    manifest = dict(schema_version=2, run_id=run_id, created_utc=now.isoformat(),
        research_status=protocol["status"], protocol_sha256=digest(config_path),
        source_hashes={str(p.relative_to(root)): digest(p) for p in sorted((root/"src/roaring_returns").glob("*.py"))},
        numerical_source_hashes={f"src/roaring_returns/{name}": digest(root/"src/roaring_returns"/name)
                                 for name in numerical_modules},
        data=data_metadata, windows=windows, configurations=len(summary),
        software=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                      cvxpy=cvxpy.__version__, clarabel=clarabel.__version__),
        failures=failures, disclosure="Causal decisions on already-inspected history; no alpha or prospective holdout claim.")
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    _write_report(output, summary, protocol, manifest)
    return output, summary


def _write_report(output, summary, protocol, manifest):
    monthly = pd.read_csv(output/"monthly_metrics.csv")
    material_counts = monthly.assign(material_sale=monthly.actual_sales_fraction_signal > 1e-6).groupby(
        ["period", "strategy"]).material_sale.sum()
    lines = ["# Execution-risk research v0.2", "", "**Exploratory retrospective study; previously inspected history.**", "",
             f"Data: {manifest['data']['source']}. {len(summary)} fixed configurations. No historical parameter search.", "",
             f"Account: USD {protocol['initial_wealth']:,.0f} + USD {protocol['monthly_contribution']:,.0f}/month; "
             f"equal targets; {protocol['band']*100:g}pp band; {protocol['cost_bps']:g}bp per purchase/sale dollar.", "",
             "Previous-close frozen dollar plans fill at next session close. Return-unit proxies with implicit income reinvestment.", "",
             f"All methods share {protocol.get('warmup_sessions', 0)} pre-decision warm-up sessions; the first requested window starts after warm-up. Exact realized start/end are in summary.csv.", "",
             "Selling-month counts below exclude sales of at most 1e-6 of signal wealth (USD 0.01 for a USD 10,000 account), uniformly across methods. The raw summary preserves the legacy >1e-7 USD count.", "",
             "| Requested window | Strategy | Post-fill RMS (pp) | Outside / months | Material selling months | Annual sales / mean wealth | Fees (USD) |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for r in summary.itertuples():
        lines.append(f"| {r.period} | {r.label} | {r.posttrade_rms_deviation_pp:.3f} | {r.violating_months}/{r.months} | "
                     f"{int(material_counts.loc[(r.period, r.strategy)])} | {100*r.annual_sales_over_mean_wealth:.2f}% | {r.total_fees:.2f} |")
    risk = pd.read_csv(output/"risk_diagnostics.csv")
    scores = risk.pivot(index="period", columns="model", values="mean_qlike")
    worse = int((scores.ridge_vol > scores.ewma).sum())
    ridge_rows = summary[summary.strategy == "cvar_sales_ridge"]
    lines += ["", "## Observed model and numerical results", "",
        f"Ridge variance QLIKE is worse than EWMA in {worse}/{len(scores)} windows (lower is better); this is not evidence that ML improved forecasts.", "",
        "| Requested window | Historical QLIKE | EWMA QLIKE | Ridge QLIKE | Ridge variance clips¹ |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for period, score in scores.iterrows():
        clips = int(ridge_rows.loc[ridge_rows.period == period, "ridge_variance_clips"].iloc[0])
        lines.append(f"| {period} | {score.historical:.3f} | {score.ewma:.3f} | {score.ridge_vol:.3f} | {clips} |")
    lines += ["", "¹ Counts asset forecasts clipped to 0.1–10× EWMA variance at monthly origins, once per risk-budget/ridge policy path; they are not independent repeated experiments.", "",
        "The tracking QPs trade toward the center and have nearly identical aggregate outcomes across covariance models at these settings. Under frozen-dollar fills, the random part of squared dollar tracking is largely independent of the trade; models matter through active tail constraints. This similarity is not evidence of learned robustness.", "",
        "The analytic buffer is a strong inexpensive comparator. Risk-budget LPs do not establish superiority over it; inspect selling, drift and fees together. Published paired intervals compare against signal minimum sale, not directly against the buffer.", "",
        f"Same-program solver retries: {int(summary.solver_retry_months.sum())}; LP-only months with incomplete target-nearest tie-break: {int(summary.tie_break_incomplete_months.sum())}. Counts are strategy-month solves, not unique market dates.", "",
        f"Risk-budget slack months above 1e-6 normalized capital: {int(summary.loc[summary.strategy.str.startswith('cvar_sales'), 'risk_slack_months'].sum())}. Zero means the soft budget was not materially relaxed on these paths; it does not guarantee future feasibility.", ""]
    lines += ["", "## Interpretation contract", "",
              "- Compare violation counts and sizes together with selling, fees, and post-fill RMS. Lower drift alone is not superiority.",
              "- The analytic buffer is a first-order, per-asset approximation, not a joint 95% guarantee.",
              "- Scenario QPs optimize squared dollar tracking, gross trading penalty, and finite-scenario CVaR. They do not minimize the original static sale bound.",
              f"- Risk-budget sales policies minimize sales plus {protocol['tail_slack_penalty']:g} times soft risk-budget slack. Risk budget is {protocol['tail_budget']:g} of signal-plus-flow capital; all excess slack is reported. A tracking tie-break stays within 1e-6 of the primary objective and caps sales/slack separately at the LP solution (1e-9/1e-10 normalized roundoff); a buy-only optimal face enforces zero sales. Tracking cannot spend the main tolerance on micro-sales.",
              "- A failed tie-break retries the same QP with OSQP, then preserves the verified first-stage LP solution if necessary. `tie_break_incomplete_months` explicitly counts those cases; they do not have the target-nearest guarantee. A failed first-stage solve or feasibility check aborts the study.",
              "- CVaR is on normalized dollar excess, not exact percentage-weight excess. The denominator is fixed signal wealth plus contribution.",
              "- Scenarios use every available one of the last 252 causally filtered joint historical residuals. Designed stress shocks are excluded from the default distribution and remain separate demo what-if inputs. Tail levels are not calibrated real-market probabilities.",
              "- Ridge estimates next-session variance using matured labels. It does not forecast alpha or train through the optimizer.",
              "- `risk_diagnostics.csv` scores next execution-session variance QLIKE, independently of which trading policy is selected.",
              "- `paired_intervals.csv` resamples paired monthly outcomes in six-month circular blocks. These are conditional descriptive intervals, not full refit/path bootstrap or new out-of-sample evidence.",
              "- Legacy rules leave proportional-cost scaling to the fill engine; the QPs anticipate those fees in their budget. `fill_adjusted_months` exposes resulting adjustments.",
              "- Market impact, taxes, share granularity, live execution, and spendable dividend-cash accounting are outside this experiment.",
              "", "All settings, numerical source hashes, cached data hash, environment, and solver failures are recorded in manifest.json."]
    lines += ["", "![Matched execution-risk comparison](tradeoffs.png)"]
    (output/"REPORT.md").write_text("\n".join(lines)+"\n")
    _plot_tradeoffs(summary, output/"tradeoffs.png")


def _plot_tradeoffs(summary, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    styles = {"min_sales_band": ("Signal minimum sale", "#97a2b0"),
              "buffered_band": ("Analytic buffer", "#445c79"),
              "cvar_sales_ewma": ("Risk budget / EWMA", "#168a94"),
              "cvar_sales_ridge": ("Risk budget / ridge", "#b78b32")}
    periods = list(summary.period.unique())
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(1, len(periods), figsize=(12, 4.3), squeeze=False)
        for ax, period in zip(axes.flat, periods):
            data = summary[summary.period == period].set_index("strategy")
            for strategy, (label, color) in styles.items():
                row = data.loc[strategy]
                ax.scatter(100*row.annual_sales_over_mean_wealth, row.posttrade_rms_deviation_pp,
                           s=85, color=color, label=label, edgecolor="white", linewidth=.7)
            ax.set(title=period, xlabel="Annual sales / mean wealth (%)",
                   ylabel="Post-fill RMS deviation (pp)")
            ax.grid(alpha=.15)
        fig.suptitle("Execution-risk controls: drift and selling together", weight="bold", y=.98)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(.5, .015))
        fig.text(.5, .095, "Exploratory history or synthetic mechanisms; fixed 2bp costs. Neither axis alone establishes superiority.",
                 ha="center", fontsize=9, color="#566271")
        fig.tight_layout(rect=(0, .17, 1, .94))
        fig.savefig(path, dpi=180, facecolor="white")
        plt.close(fig)


def publish_study(run, destination):
    """Export aggregate derived results only; no raw prices or full daily ledger."""
    import shutil
    run, destination = Path(run), Path(destination)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite public export: {destination}")
    destination.mkdir(parents=True)
    for name in ("summary.csv", "monthly_metrics.csv", "monthly_curves.csv", "paired_intervals.csv",
                 "risk_diagnostics.csv", "manifest.json", "protocol.json", "REPORT.md", "tradeoffs.png"):
        shutil.copy2(run/name, destination/name)
    hashes = {p.name: digest(p) for p in sorted(destination.iterdir()) if p.is_file()}
    (destination/"artifact_hashes.json").write_text(json.dumps(hashes, indent=2)+"\n")
    return destination
