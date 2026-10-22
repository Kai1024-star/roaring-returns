"""Versioned multi-asset snapshots. Raw vendor data stays local and immutable.

Close is a historical vendor quote (split adjusted), not an executable quote.
Adjusted close is a reinvested distribution return proxy, not a spot price.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import numpy as np
import pandas as pd
import requests
from .data import digest, parse_chart

UNIVERSE = {
    'BIL': ('Treasury-bill fund / cash proxy', 'Cash'),
    'SPY': ('US large-cap stocks', 'Equities'),
    'QQQ': ('Nasdaq-100 stocks', 'Equities'),
    'IWM': ('US small-cap stocks', 'Equities'),
    'VEA': ('Developed ex-US stocks', 'Equities'),
    'VWO': ('Emerging-market stocks', 'Equities'),
    'GLD': ('Gold fund', 'Commodities'),
    'SLV': ('Silver fund', 'Commodities'),
    'USO': ('Oil futures fund — not spot crude', 'Commodities'),
    'SHY': ('1–3y Treasury fund', 'Bonds'),
    'IEF': ('7–10y Treasury fund', 'Bonds'),
    'TLT': ('20+y Treasury fund', 'Bonds'),
    'TIP': ('Inflation-protected Treasury fund', 'Bonds'),
}


def completed_date(now=None):
    now = now or datetime.now(ZoneInfo('America/New_York'))
    now = now.astimezone(ZoneInfo('America/New_York'))
    return (now.date() if now.hour >= 17 else now.date()-timedelta(days=1)).isoformat()


def fetch_market(root, cutoff=None):
    root, cutoff = Path(root), cutoff or completed_date()
    raw = root/'data/raw/market_v5'/cutoff
    processed = root/'data/processed/market_v5'/cutoff
    raw.mkdir(parents=True, exist_ok=True); processed.mkdir(parents=True, exist_ok=True)
    manifest_path = raw/'manifest.json'
    if manifest_path.exists():
        return load_market(root, cutoff)[2]
    def fetch(symbol):
        path = raw/f'{symbol}.json'
        if not path.exists():
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
            response = requests.get(url, params={
                'period1': int(pd.Timestamp('1993-01-01',tz='UTC').timestamp()),
                'period2': int((pd.Timestamp(cutoff,tz='UTC')+pd.Timedelta(days=1)).timestamp()),
                'interval':'1d', 'events':'div,splits'},
                headers={'User-Agent':'Mozilla/5.0'}, timeout=40)
            response.raise_for_status()
            parse_chart(response.json(),symbol)
            path.write_bytes(response.content)
        frame = parse_chart(json.loads(path.read_bytes()),symbol).loc[:cutoff]
        r = frame.adj_close.pct_change(fill_method=None)
        ordinary = frame.dividend_ex_date_amount.eq(0)
        error = float((r-frame.close.pct_change(fill_method=None))[ordinary].abs().max())
        if error > 2e-5 or (r.abs() > .65).any() or len(frame) < 1000:
            raise ValueError(f'{symbol}: return/split/coverage audit failed; inspect snapshot.')
        entry = dict(symbol=symbol, sha256=digest(path), rows=len(frame),
                     first_date=str(frame.index[0].date()), last_date=str(frame.index[-1].date()),
                     last_close=float(frame.close.iloc[-1]),
                     ordinary_return_max_difference=error,
                     splits=int(frame.split_ratio.ne(0).sum()),
                     source='Yahoo Finance chart endpoint; same-provider checks only')
        return symbol, frame, entry
    with ThreadPoolExecutor(max_workers=3) as pool:
        fetched = list(pool.map(fetch, UNIVERSE))
    frames = {symbol:frame for symbol,frame,_ in fetched}
    first = max(f.index[0] for f in frames.values())
    last = min(f.index[-1] for f in frames.values())
    index = frames['BIL'].loc[first:last].index
    if any(not f.loc[first:last].index.equals(index) for f in frames.values()):
        raise ValueError('Market calendars disagree; missing prices are not filled.')
    adjusted = pd.DataFrame({s:f.adj_close.loc[index] for s,f in frames.items()})
    quotes = pd.DataFrame({s:f.close.loc[index] for s,f in frames.items()})
    adjusted.to_csv(processed/'adjusted.csv',float_format='%.12g')
    quotes.to_csv(processed/'quotes.csv',float_format='%.12g')
    manifest = dict(schema=1, cutoff=cutoff, created_utc=datetime.now(timezone.utc).isoformat(),
                    source='Yahoo Finance daily chart snapshots', independent_provider_validated=False,
                    assets=list(UNIVERSE), first_date=str(first.date()), last_date=str(last.date()),
                    common_rows=len(index), files=[entry for _,_,entry in fetched],
                    processed={name:digest(processed/name) for name in ['adjusted.csv','quotes.csv']},
                    note='Adjusted closes are total-return proxies. USO is a futures fund, not spot crude. No raw redistribution.')
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    (root/'data/raw/market_v5/latest.json').write_text(json.dumps({'cutoff':cutoff})+'\n')
    return manifest


def load_market(root, cutoff=None):
    root = Path(root)
    if cutoff is None:
        cutoff = json.loads((root/'data/raw/market_v5/latest.json').read_text())['cutoff']
    meta = json.loads((root/'data/raw/market_v5'/cutoff/'manifest.json').read_text())
    for entry in meta['files']:
        if digest(root/'data/raw/market_v5'/cutoff/(entry['symbol']+'.json'))!=entry['sha256']:
            raise ValueError('Raw market snapshot hash changed.')
    processed = root/'data/processed/market_v5'/cutoff
    frames = []
    for name in ['adjusted.csv','quotes.csv']:
        if digest(processed/name) != meta['processed'][name]:
            raise ValueError('Market snapshot hash changed.')
        frame = pd.read_csv(processed/name,index_col='date',parse_dates=True)
        if list(frame.columns) != meta['assets'] or not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
            raise ValueError('Invalid market snapshot.')
        frames.append(frame)
    if (not frames[0].index.equals(frames[1].index) or frames[0].index.has_duplicates
            or not frames[0].index.is_monotonic_increasing):
        raise ValueError('Invalid cached market calendar.')
    return *frames, meta


def market_or_synthetic(root):
    if (Path(root)/'data/raw/market_v5/latest.json').exists():
        a,q,m = load_market(root)
        return a,q,m,False
    rng = np.random.default_rng(705)
    dates = pd.bdate_range('2005-01-03','2025-12-31')
    common = rng.normal(size=(len(dates),3))
    loadings = np.array([[.01,.01,.01]]+[[.6,.1,.1]]*5+[[.1,.6,.1]]*3+[[.05,.1,.65]]*4)
    noise = common@loadings.T+rng.normal(0,.5,(len(dates),13))
    sigmas = np.array([.0001]+[.012]*5+[.012,.02,.025]+[.002,.005,.009,.004])
    logs = noise*sigmas+.00012
    values = pd.DataFrame(100*np.exp(logs.cumsum(0)),index=dates,columns=UNIVERSE)
    values.index.name='date'
    return values,values.copy(),dict(source='SYNTHETIC demonstration, not observed prices',
        first_date=str(dates[0].date()),last_date=str(dates[-1].date()),common_rows=len(dates),
        assets=list(UNIVERSE), processed={'adjusted.csv':__import__('hashlib').sha256(values.to_csv().encode()).hexdigest()}),True
