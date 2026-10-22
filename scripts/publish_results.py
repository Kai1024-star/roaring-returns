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
    manifest = {p.name: sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir()) if p.is_file() and p.name != 'artifact_hashes.json'}
    (output / 'artifact_hashes.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Exported {len(manifest)} aggregate artifacts to {output}')


if __name__ == '__main__':
    main()
