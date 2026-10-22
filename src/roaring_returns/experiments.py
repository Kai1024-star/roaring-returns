"""Frozen-scenario runner; development, validation and evaluation stay separate."""

from hashlib import sha256
import itertools
import json
from pathlib import Path
import os
import numpy as np
import pandas as pd
from . import __version__
from .data import load_prices
from .engine import BacktestConfig, backtest, summarize


def window_with_anchor(prices, start, end):
    before = prices.loc[prices.index < pd.Timestamp(start)].tail(1)
    inside = prices.loc[start:end]
    if len(before) != 1 or len(inside) < 2:
        raise ValueError("A previous-session anchor and at least two sessions are required.")
    return pd.concat((before, inside))


def run_experiments(root, split="development"):
    root = Path(root)
    protocol_path = root / "configs/baseline.json"
    protocol = json.loads(protocol_path.read_text())
    if split not in protocol["splits"]:
        raise ValueError("Unknown chronological split.")
    prices, manifest = load_prices(root)
    prices = prices[protocol["assets"]]
    start, end = protocol["splits"][split]
    prices = window_with_anchor(prices, start, end)
    output = root / "reports/runs" / split
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    representative = {}
    rep_wealth = 10000 if 10000 in protocol["initial_wealth"] else protocol["initial_wealth"][0]
    rep_cash = 100 if 100 in protocol["monthly_contributions"] else protocol["monthly_contributions"][0]
    for wealth, cash, strategy in itertools.product(protocol["initial_wealth"],
                                                     protocol["monthly_contributions"],
                                                     protocol["strategies"]):
        cfg = BacktestConfig(strategy=strategy, initial_wealth=wealth, monthly_contribution=cash,
                             target=tuple(protocol["target"]), band=protocol["band"],
                             cost_bps=protocol["cost_bps"])
        result = backtest(prices, cfg)
        summary = dict(strategy=strategy, initial_wealth=wealth, monthly_contribution=cash,
                       split=split, cost_bps=cfg.cost_bps, **summarize(result))
        summaries.append(summary)
        if wealth == rep_wealth and cash == rep_cash:
            representative[strategy] = result
            result.daily.to_csv(output / f"daily_{strategy}.csv.gz", compression="gzip", float_format="%.12g")
            result.events.to_csv(output / f"events_{strategy}.csv", index=False, float_format="%.12g")
    summary_frame = pd.DataFrame(summaries)
    summary_frame.to_csv(output / "summary.csv", index=False, float_format="%.12g")
    # Separate, declared implementation stress: one-way 10bp, not a broker's fee quote.
    stress = []
    for strategy in protocol["strategies"]:
        cfg = BacktestConfig(strategy=strategy, initial_wealth=rep_wealth, monthly_contribution=rep_cash,
                             target=tuple(protocol["target"]), band=protocol["band"], cost_bps=10)
        stress.append(dict(strategy=strategy, cost_bps=10, **summarize(backtest(prices, cfg))))
    pd.DataFrame(stress).to_csv(output / "cost_stress_10bps.csv", index=False, float_format="%.12g")
    sensitivity = []
    for band, strategy in itertools.product(protocol["band_sensitivity"], protocol["strategies"]):
        cfg = BacktestConfig(strategy=strategy, initial_wealth=rep_wealth, monthly_contribution=rep_cash,
                             target=tuple(protocol["target"]), band=band, cost_bps=protocol["cost_bps"])
        sensitivity.append(dict(strategy=strategy, band=band, **summarize(backtest(prices, cfg))))
    band_frame = pd.DataFrame(sensitivity)
    band_frame.to_csv(output / "band_sensitivity.csv", index=False, float_format="%.12g")
    code_files = sorted((root / "src/roaring_returns").glob("*.py"))
    record = dict(package_version=__version__, split=split, start=start, end=end,
                  protocol_sha256=sha256(protocol_path.read_bytes()).hexdigest(),
                  data_sha256=manifest["processed_sha256"],
                  code_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in code_files},
                  sessions=len(prices), scenario_count=len(summaries),
                  assets=protocol["assets"], target=protocol["target"], band=protocol["band"],
                  band_sensitivity=protocol["band_sensitivity"],
                  representative_initial_wealth=rep_wealth, representative_monthly_contribution=rep_cash,
                  limitations=["retrospective chosen ETF universe", "single public vendor; not independently certified",
                               "total-return-unit fractional model; no whole-share or tax claims",
                               "lagged close dollar fills; idealized liquidity, no market impact",
                               "zero cash interest; distributions implicitly reinvested in original asset",
                               "minimum-sale theorem applies at signal prices without costs, not at delayed fills"],
                  execution=protocol["execution"])
    (output / "run_manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    (output / "protocol_snapshot.json").write_text(json.dumps(protocol, indent=2) + "\n")
    (output / "data_manifest_snapshot.json").write_text(json.dumps(manifest, indent=2) + "\n")
    plot_results(output, summary_frame, representative, band_frame, protocol["band"], split, rep_wealth, rep_cash)
    write_report(output, summary_frame, manifest, record)
    return output, summary_frame


def plot_results(output, summary, representative, band_frame, band, split, rep_wealth, rep_cash):
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    colors = dict(zip(representative, ["#94a3b8", "#d97706", "#2563eb", "#16a34a", "#9333ea"]))
    sample = next(iter(representative.values())).daily
    period = f"{sample.index[1].year}–{sample.index[-1].year}"
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for strategy, result in representative.items():
        metrics = summarize(result)
        ax.scatter(metrics["annual_sales_over_mean_wealth"]*100, metrics["signal_rms_deviation_pp"],
                   label=strategy, s=90, color=colors[strategy])
    ax.set(xlabel="Annual sales / mean wealth (%)", ylabel="Signal-date RMS allocation deviation (pp)",
           title=f"{split.capitalize()} {period} · USD {rep_wealth:,.0f} + USD {rep_cash:,.0f}/month")
    ax.legend(fontsize=8); ax.grid(alpha=.15)
    fig.tight_layout(); fig.savefig(output / "drift_vs_selling.png", dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5.4))
    for strategy in representative:
        group = band_frame[band_frame.strategy == strategy].sort_values("band")
        if strategy in ("threshold_center", "min_sales_band"):
            ax.plot(group.annual_sales_over_mean_wealth*100, group.signal_rms_deviation_pp,
                    marker="o", label=strategy, color=colors[strategy])
            for _, row in group.iterrows():
                ax.annotate(f"{row.band*100:g}pp", (row.annual_sales_over_mean_wealth*100, row.signal_rms_deviation_pp),
                            xytext=(6, 5), textcoords="offset points", fontsize=8)
        else:
            row = group.iloc[0]
            ax.scatter(row.annual_sales_over_mean_wealth*100, row.signal_rms_deviation_pp,
                       label=strategy, color=colors[strategy], s=65)
    ax.set(xlabel="Annual sales / mean wealth (%)", ylabel="Signal-date RMS allocation deviation (pp)",
           title=f"{split.capitalize()} {period}: prespecified band sensitivity · fractional model")
    ax.legend(fontsize=8); ax.grid(alpha=.15)
    fig.tight_layout(); fig.savefig(output / "band_sensitivity.png", dpi=160); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for strategy, result in representative.items():
        axes[0].plot(result.daily.index, result.daily.nav, label=strategy, color=colors[strategy], lw=1.4)
        monthly = result.daily.max_deviation_pp.resample("ME").last()
        axes[1].plot(monthly.index, monthly, color=colors[strategy], lw=1.1)
    axes[0].set(ylabel="Unitized wealth (external deposits removed)", title=f"{split.capitalize()} {period}: return and allocation drift")
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].axhline(band*100, color="#334155", linestyle="--", lw=1)
    axes[1].set(ylabel="Largest allocation deviation (pp)", xlabel="Date")
    for ax in axes: ax.grid(alpha=.15)
    fig.tight_layout(); fig.savefig(output / "return_and_drift.png", dpi=160); plt.close(fig)
    subset = summary[summary.strategy == "cashflow_only"]
    pivot = subset.pivot(index="initial_wealth", columns="monthly_contribution", values="outside_band_fraction")
    fig, ax = plt.subplots(figsize=(7.8, 4.5))
    im = ax.imshow(pivot.to_numpy()*100, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)), [f"${v:,.0f}" for v in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), [f"${v:,.0f}" for v in pivot.index])
    for (i, j), value in np.ndenumerate(pivot.to_numpy()):
        ax.text(j, i, f"{value:.1%}", ha="center", va="center", color="black" if value < .65 else "white")
    ax.set(xlabel="Fixed monthly external contribution", ylabel="Initial wealth",
           title=f"{split.capitalize()} {period}: buy-only sessions outside ±{band*100:g}pp")
    fig.colorbar(im, ax=ax, label="Outside band (%)")
    fig.tight_layout(); fig.savefig(output / "contribution_map.png", dpi=160); plt.close(fig)


def write_report(output, summary, data_manifest, run):
    rep_w, rep_c = run["representative_initial_wealth"], run["representative_monthly_contribution"]
    rows = summary[(summary.initial_wealth == rep_w) & (summary.monthly_contribution == rep_c)]
    table = ["| Strategy | Signal RMS (pp) | Post-trade RMS (pp) | Post-trade outside band | Annual sales / mean wealth |",
             "|---|---:|---:|---:|---:|"]
    for _, r in rows.iterrows():
        table.append(f"| {r.strategy} | {r.signal_rms_deviation_pp:.3f} | {r.posttrade_rms_deviation_pp:.3f} | {r.posttrade_outside_band_fraction:.1%} | {r.annual_sales_over_mean_wealth:.1%} |")
    target_description = ", ".join(f"{s} {a:.2%}" for s, a in zip(run["assets"], run["target"]))
    hybrid = rows.loc[rows.strategy == "min_sales_band"].iloc[0]
    fill_caution = (f"In the representative account, the signal-price minimum-sale plan "
                    f"finished outside its own band in {hybrid.selling_posttrade_outside_fraction:.1%} "
                    f"of months with positive sales. This is a measured execution limitation; "
                    f"the report does not retune a buffer to conceal it.")
    text = f"""# Roaring Returns — {run['split']} run

Python research prototype v{__version__}. This is an exploratory implementation result,
not evidence of a novel strategy or a completed investment recommendation.

Period: {run['start']} to {run['end']}; {run['scenario_count']} scenarios plus a separate
10bp cost stress. Each scenario starts afresh at the previous-session close.
Target: {target_description}; baseline band: ±{run['band']*100:g} percentage points.
Prespecified sensitivity bands: {', '.join(f'{v*100:g}pp' for v in run['band_sensitivity'])}.

## Representative account: USD {rep_w:,.0f} + USD {rep_c:,.0f} each month

{chr(10).join(table)}

![Deviation versus sales](drift_vs_selling.png)
![Band sensitivity](band_sensitivity.png)
![Unitized returns and drift](return_and_drift.png)
![Contribution intensity scenarios](contribution_map.png)

## Interpretation and limits

Zero sales in the buy-only rules is a constraint, not a finding. Read its drift
alongside it. The hybrid's low sales are a one-state implementation objective,
not a proof of best cumulative trading or best returns. Baselines receive the
same monthly contributions, and thresholds and weights are not chosen from
these results. Daily observations on one history are not independent samples.
Primary deviation metrics use the same signal dates and execution dates for all
rules. Daily outside-band frequency remains a secondary path exposure measure:
a boundary rule is naturally more likely to cross its band than a center reset.
Band-sensitivity points are descriptive comparisons, not a proven efficient
frontier or a reason to select the best historical width. With zero new cash,
proportional and buy-only rules coincide; duplicate controls are kept transparent.

{fill_caution}

Orders are planned from the previous close and executed in fixed dollars at the
next session close. Existing holdings earn that session's return before external
cash arrives. TWR links the pre-flow market factor and post-flow execution factor.
Fees reduce wealth; buys are reduced if needed to avoid borrowing. Consequently,
delayed or cost-adjusted fills need not restore the ideal frictionless band.

Data: Yahoo Finance publicly accessible chart data; vendor adjusted-close ratios
are a **total-return proxy**, with implicit reinvestment in the original asset.
No separate dividend cash is added. These are normalized fractional return units,
not historical executable ETF share prices. Pay-date income, whole shares, taxes,
bid/ask spread dynamics, and market impact are not implemented. Cash earns zero.
The provider has not been independently certified against CRSP or another vendor.

Data hash: `{run['data_sha256']}`. Protocol hash: `{run['protocol_sha256']}`.
See `run_manifest.json`, event CSVs, and `summary.csv` for auditable details.
Raw data acquisition dates and hashes are in `data/raw/manifest.json`.

Full cached data span: {data_manifest['files'][0]['first_date']} to
{data_manifest['files'][0]['last_date']}. Chronological splits are explicit in
`configs/baseline.json`; running development does not run evaluation.

## Data resources for the next version

- [Public reader behavior / adjustment documentation](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html)
- [Columbia WRDS access](https://guides.library.columbia.edu/WRDS/overview)
- [Columbia subscribed data collections](https://guides.library.columbia.edu/WRDS/collection)
- [Time-weighted return principles](https://www.gipsstandards.org/standards/gips-standards-for-asset-owners/gips-standards-handbook-for-asset-owners/)

Before a pay-date/whole-share extension, obtain prices, split factors, distribution
amounts, ex-dates and payment dates under a verified data contract. Do not turn
adjusted-close levels into integer historical share counts.
"""
    (output / "RESEARCH_REPORT.md").write_text(text)
