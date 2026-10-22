"""Offline source, ledger, scenario-partition and allocation audit."""
from pathlib import Path
from hashlib import sha256
import json
import numpy as np
import pandas as pd

root=Path(__file__).resolve().parents[1]
folder=root/'results/market_v5'
manifest=json.loads((folder/'manifest.json').read_text())
for name,expected in manifest['numerical_module_hashes'].items():
    assert sha256((root/'src/roaring_returns'/name).read_bytes()).hexdigest()==expected,name
for name,expected in manifest['artifact_hashes'].items():
    assert sha256((folder/name).read_bytes()).hexdigest()==expected,name
summary=pd.read_csv(folder/'summary.csv')
assert len(summary)==manifest['case_count']==32
assert summary.pnl_reconciliation_error.max()<1e-6
groups=pd.read_csv(folder/'scenario_groups.csv')
for case,frame in groups.groupby('case_id'):
    assert frame['count'].sum()==manifest['paths_per_case']
    assert abs(frame.share.sum()-1)<1e-12
    assert frame.iloc[0]['count']==frame['count'].max()
    assert ((frame.representative>=0)&(frame.representative<manifest['paths_per_case'])).all()
weights=pd.read_csv(folder/'weights.csv')
for _,frame in weights.groupby(['universe','model','allocation']):
    assert abs(frame.weight.sum()-1)<1e-8
    if frame.allocation.iloc[0]=='Class example':continue
    assert abs(frame.loc[frame.fund=='BIL','weight'].iloc[0]-.1)<1e-7
    assert frame.loc[frame.fund!='BIL','weight'].max()<=.4500001
    assert frame.loc[frame.fund.isin(['SPY','QQQ','IWM','VEA','VWO']),'weight'].sum()>=.3999999
    assert frame.loc[frame.fund.isin(['GLD','SLV','USO']),'weight'].sum()<=.2000001
    assert frame.loc[frame.fund=='USO','weight'].sum()<=.1000001
print(json.dumps(dict(source_modules=len(manifest['numerical_module_hashes']),cases=len(summary),
    scenario_group_rows=len(groups),maximum_pnl_error=float(summary.pnl_reconciliation_error.max())),indent=2))
