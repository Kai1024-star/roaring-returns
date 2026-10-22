"""Verify public v0.4 aggregates against their source/artifact hashes, offline."""
from hashlib import sha256
import json
from pathlib import Path
import pandas as pd

root=Path(__file__).resolve().parents[1]
folder=root/'results/planner_v4'
manifest=json.loads((folder/'manifest.json').read_text())
for name,expected in manifest['numerical_module_hashes'].items():
    assert sha256((root/'src/roaring_returns'/name).read_bytes()).hexdigest()==expected,name
for name,expected in manifest['artifact_hashes'].items():
    assert sha256((folder/name).read_bytes()).hexdigest()==expected,name
expected_rows={'scenario_comparison.csv':18,'sensitivity.csv':6,'historical_replays.csv':18}
for name,count in expected_rows.items():
    assert len(pd.read_csv(folder/name))==count,name
history=pd.read_csv(folder/'historical_replays.csv')
assert history.pnl_reconciliation_error.max()<1e-6
fits=json.loads((folder/'causal_model_fits.json').read_text())
starts={'2008–09':'2008-09-01','2020':'2020-02-01','2022':'2022-01-01'}
for fit in fits:
    assert fit['estimated_through'] < starts[fit['event']]
    assert fit['observations']==756
    assert max(abs(value-1/3) for value in fit['risk_shares'])<2e-5
print(json.dumps({'source_modules':len(manifest['numerical_module_hashes']),'tables':expected_rows,
    'maximum_pnl_reconciliation_error':float(history.pnl_reconciliation_error.max()),'causal_fits':len(fits)},indent=2))
