"""Export aggregate research artifacts, excluding raw data and daily ledgers.

Run after all three baseline segments. Files are flattened so each segment's
provenance and plots travel together in a small public results directory.
"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ('development', 'validation', 'evaluation')
ARTIFACTS = ('summary.csv', 'band_sensitivity.csv', 'cost_stress_10bps.csv',
             'drift_vs_selling.png', 'band_sensitivity.png',
             'return_and_drift.png', 'contribution_map.png',
             'run_manifest.json', 'protocol_snapshot.json',
             'data_manifest_snapshot.json', 'RESEARCH_REPORT.md')


def main():
    output = ROOT / 'results'
    output.mkdir(exist_ok=True)
    rows = []
    all_cases = []
    for split in SPLITS:
        source = ROOT / 'reports/runs' / split
        for name in ARTIFACTS:
            origin = source / name
            target = output / f'{split}_{name}'
            if name.endswith('.md'):
                text = origin.read_text().replace('minimum-sale theorem', 'minimum-sale bound')
                text = text.replace('The provider has not been independently certified against CRSP or another vendor.',
                                    'Returns were not cross-checked against CRSP or any second provider; only same-snapshot internal checks were run.')
                text = text.replace('The hybrid\'s low sales', 'The hybrid (min_sales_band)\'s low sales')
                text += ('\nWidth values were in the early design; sensitivity analysis was added after '
                         'the first development run and before later-period outcomes were inspected. '
                         'The 10bp stress charges each gross purchase and sale amount; it is not a broker quote. '
                         'TWR removes external-flow timing; investor dollar outcomes differ and money-weighted '
                         'returns are not computed.\n')
                for artifact in ARTIFACTS:
                    text = text.replace(f']({artifact})', f']({split}_{artifact})')
                text = text.replace('See `run_manifest.json`, event CSVs, and `summary.csv`',
                                    f'See `{split}_run_manifest.json` and `{split}_summary.csv`')
                text = text.replace('Raw data acquisition dates and hashes are in `data/raw/manifest.json`.',
                                    f'Acquisition dates and hashes are in `{split}_data_manifest_snapshot.json`. '
                                    'Raw prices and detailed ledgers stay local.')
                target.write_text(text)
            else:
                shutil.copyfile(origin, target)
        frame = pd.read_csv(source / 'summary.csv')
        all_cases.append(frame)
        selected = frame[(frame.initial_wealth == 10000) & (frame.monthly_contribution == 100)]
        rows.extend(selected.to_dict('records'))
    all_cases = pd.concat(all_cases, ignore_index=True)
    all_cases.to_csv(output / 'all_baseline_summary.csv', index=False, float_format='%.12g')
    representative = pd.DataFrame(rows)
    representative.to_csv(output / 'representative_summary.csv', index=False, float_format='%.12g')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    palette = ['#94a3b8', '#d97706', '#2563eb', '#16a34a', '#9333ea']
    for ax, split in zip(axes, SPLITS):
        for color, row in zip(palette, representative[representative.split == split].itertuples()):
            ax.scatter(row.annual_sales_over_mean_wealth*100, row.signal_rms_deviation_pp,
                       color=color, label=row.strategy, s=65)
        ax.set(title=split.capitalize(), xlabel='Annual sales / mean wealth (%)')
        ax.grid(alpha=.15)
    axes[0].set_ylabel('Signal-date RMS deviation (pp)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=5, fontsize=8)
    fig.suptitle('Fixed equal weights · USD 10,000 + USD 100/month · zero-cost baseline')
    fig.tight_layout(rect=(0, .10, 1, .94))
    fig.savefig(output / 'period_comparison.png', dpi=160)
    plt.close(fig)
    table = ['| Period | Rule | Signal RMS (pp) | Annual sales / mean wealth | Post-fill outside band |',
             '|---|---|---:|---:|---:|']
    for row in representative.itertuples():
        table.append(f'| {row.split} | {row.strategy} | {row.signal_rms_deviation_pp:.3f} | '
                     f'{row.annual_sales_over_mean_wealth:.2%} | {row.posttrade_outside_band_fraction:.1%} |')
    text = '''# Historical results

Generated from the frozen v0.1 baseline. There are 45 main scenarios per segment
(135 total), plus 15 width and 5 cost cases per segment. Three C=0 buy-only
scenarios duplicate their proportional controls within each segment.
Each segment is an independently initialized account, not a continuous account.
These are retrospective case studies on a chosen ETF universe. There are no
confidence intervals, prospective record, or strategy-superiority claims.

![Period comparison](period_comparison.png)

## USD 10,000 initial wealth + USD 100/month

'''+ '\n'.join(table)+'''

The signal-price minimum-sale plan trades off drift against selling; its static
optimality is not a guarantee of best cumulative sales or post-fill compliance.
A delayed band-edge order can cross the band before it fills. Check post-trade
metrics and each report's selling-month failure rate alongside signal metrics.
Return is secondary; allocation drift is not itself financial risk. No band or
target was changed after observing validation/evaluation outcomes.

## Full reports and audit trail

'''+ '\n'.join(f'- [{s.capitalize()} report]({s}_RESEARCH_REPORT.md)' for s in SPLITS)+'''

CSV tables contain aggregate model outputs, not vendor price histories. Raw
provider snapshots, processed return indices, per-session/per-asset ledgers and
local credentials are excluded. Download locally using the included fetcher.
Manifests retain snapshot hashes, acquisition times, code hashes, and parameters.
A fresh provider download may revise historical adjustments, so matching the
original hashes is necessary for exact numeric replication.
'''
    (output / 'README.md').write_text(text)
    write_interpretation(output, all_cases, representative)
    manifest = {p.name: sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir()) if p.is_file() and p.name != 'artifact_hashes.json'}
    (output / 'artifact_hashes.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Exported {len(manifest)} aggregate artifacts to {output}')


def write_interpretation(output, all_cases, representative):
    """Descriptive follow-up; no strategy or parameter changes."""
    import numpy as np
    import matplotlib.pyplot as plt
    audits, reachability, comparisons = [], [], []
    for split in SPLITS:
        source = ROOT / 'reports/runs' / split
        e = pd.read_csv(source / 'events_min_sales_band.csv')
        selling = e.actual_sales > 1e-7
        outside = e.posttrade_outside_band
        overshoot = e.loc[selling & outside, 'posttrade_max_deviation_pp'] - 5
        audits.append(dict(split=split, selling_months=int(selling.sum()),
                           outside_selling_months=int((selling & outside).sum()),
                           all_months=len(e), outside_all_months=int(outside.sum()),
                           median_overshoot_pp=float(overshoot.median()),
                           max_overshoot_pp=float(overshoot.max())))
        e = pd.read_csv(source / 'events_cashflow_only.csv')
        reachability.append(dict(split=split,
            exact_target_reachable_fraction=float(e.signal_exact_target_reachable.mean()),
            band_reachable_fraction=float(e.signal_buy_only_band_reachable.mean()),
            first_C_over_signal_wealth=float(e.contribution_ratio_signal.iloc[0]),
            last_C_over_signal_wealth=float(e.contribution_ratio_signal.iloc[-1])))
        widths = pd.read_csv(source / 'band_sensitivity.csv')
        for strategy, band in (('min_sales_band', .02), ('threshold_center', .05)):
            row = widths[(widths.strategy == strategy) & np.isclose(widths.band, band)].iloc[0]
            comparisons.append(dict(split=split, strategy=strategy, band_pp=band*100,
                signal_rms_pp=row.signal_rms_deviation_pp,
                posttrade_rms_pp=row.posttrade_rms_deviation_pp,
                annual_sales_fraction=row.annual_sales_over_mean_wealth,
                selling_months=int(row.selling_months),
                outside_own_band_fraction=row.posttrade_outside_band_fraction))
    pd.DataFrame(audits).to_csv(output / 'execution_audit.csv', index=False, float_format='%.12g')
    pd.DataFrame(reachability).to_csv(output / 'buy_only_reachability.csv', index=False, float_format='%.12g')
    pd.DataFrame(comparisons).to_csv(output / 'cross_band_comparison.csv', index=False, float_format='%.12g')
    buy_only = all_cases[all_cases.strategy == 'cashflow_only']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3), sharey=True)
    ceiling = float(buy_only.signal_rms_deviation_pp.max())
    for ax, split in zip(axes, SPLITS):
        table = buy_only[buy_only.split == split].pivot(
            index='initial_wealth', columns='monthly_contribution', values='signal_rms_deviation_pp')
        im = ax.imshow(table.to_numpy(), cmap='YlOrRd', vmin=0, vmax=ceiling, aspect='auto')
        ax.set_xticks(range(len(table.columns)), [f'${v:,.0f}' for v in table.columns])
        ax.set_yticks(range(len(table.index)), [f'${v:,.0f}' for v in table.index])
        for (i, j), value in np.ndenumerate(table.to_numpy()):
            ax.text(j, i, f'{value:.2f}', ha='center', va='center',
                    color='white' if value > ceiling*.65 else 'black')
        ax.set(title=split.capitalize(), xlabel='Fixed monthly contribution')
    axes[0].set_ylabel('Initial wealth')
    fig.suptitle('Buy-only allocation: common signal-date RMS deviation (pp)')
    fig.colorbar(im, ax=axes, label='RMS deviation (pp)', fraction=.025, pad=.03)
    fig.subplots_adjust(left=.08, right=.87, bottom=.20, top=.80, wspace=.25)
    fig.savefig(output / 'contribution_primary.png', dpi=160)
    plt.close(fig)
    lines = ['\n## Cash-flow intensity and reachability\n',
             '![Primary cash-flow comparison](contribution_primary.png)\n',
             'Larger contributions relative to initial wealth reduced buy-only drift in these',
             'cases. Initial C/W0 is a scenario label; C/W changes along each account path',
             'and can rise in losses. It is not a constant explanatory variable. The older',
             'per-period contribution maps show daily band exposure, a secondary metric.\n',
             '| Period | Buy-only RMS at C=0 (pp) | Buy-only RMS at initial C/W0=1% (pp) |',
             '|---|---:|---:|']
    for split in SPLITS:
        zero = buy_only[(buy_only.split == split) & (buy_only.monthly_contribution == 0)].iloc[0]
        rep = representative[(representative.split == split) & (representative.strategy == 'cashflow_only')].iloc[0]
        lines.append(f'| {split} | {zero.signal_rms_deviation_pp:.3f} | {rep.signal_rms_deviation_pp:.3f} |')
    lines += ['\nReachability below uses the **buy-only policy\'s carried holdings** in the',
              'representative account. These are signal-price, zero-cost feasibility',
              'fractions, not delayed-fill success rates or a calibrated forecast.\n',
              '| Period | Exact target reachable without sales | ±5pp band reachable without sales | Initial / final signal C/W |',
              '|---|---:|---:|---:|']
    for r in reachability:
        lines.append(f"| {r['split']} | {r['exact_target_reachable_fraction']:.1%} | {r['band_reachable_fraction']:.1%} | {r['first_C_over_signal_wealth']:.2%} / {r['last_C_over_signal_wealth']:.2%} |")
    lines += ['\n## Delayed execution: counts and size of violations\n',
              '| Period | Outside / selling months | Outside / all execution months | Median overshoot (pp) | Maximum overshoot (pp) |',
              '|---|---:|---:|---:|---:|']
    for r in audits:
        lines.append(f"| {r['split']} | {r['outside_selling_months']}/{r['selling_months']} | {r['outside_all_months']}/{r['all_months']} | {r['median_overshoot_pp']:.3f} | {r['max_overshoot_pp']:.3f} |")
    lines += ['\nOvershoot is max(absolute asset-weight deviation) minus 5pp, measured',
              'only in violating selling months of the representative minimum-sale plan.',
              'Small denominators (notably four selling months in validation) prevent',
              'treating percentage differences as evidence of regime deterioration.\n',
              '## Comparing different widths\n',
              'At equal 5pp bands the minimum-sale plan has less selling and greater drift',
              'than threshold-to-center. Across widths, the 2pp minimum-sale cases have',
              'both lower signal RMS and lower sale amounts than the 5pp center cases',
              'in all three segments. They also sell in more months. This is a descriptive',
              'historical observation, without uncertainty intervals or a superiority claim.\n',
              '| Period | Rule / own band | Signal RMS (pp) | Post-trade RMS (pp) | Annual sales / mean wealth | Selling months |',
              '|---|---|---:|---:|---:|---:|']
    for r in comparisons:
        lines.append(f"| {r['split']} | {r['strategy']} / {r['band_pp']:g}pp | {r['signal_rms_pp']:.3f} | {r['posttrade_rms_pp']:.3f} | {r['annual_sales_fraction']:.2%} | {r['selling_months']} |")
    lines += ['\nOutside-own-band fractions cannot be compared directly across different',
              'widths. Use RMS or a common absolute threshold. The 10pp minimum-sale and',
              'buy-only cases coincide in validation and evaluation; those points are',
              'duplicate outcomes, not independent evidence. At 5pp, annual rebalancing',
              'has both greater signal RMS and more selling than the minimum-sale rule',
              'in these representative cases; other objectives can rank them differently.\n',
              'Public report copies receive link and wording edits after generation.',
              'Their numerical tables are unchanged. Historical source hashes preserve',
              'the numerical run state; export-script changes affect presentation only.\n']
    p = output / 'README.md'
    p.write_text(p.read_text()+'\n'.join(lines))


if __name__ == '__main__':
    main()
