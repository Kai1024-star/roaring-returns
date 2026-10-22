"""Separate, immutable SPY/GLD/IEF/BIL snapshot for the budget planner.

The original QQQ research snapshot and numerical modules are never modified.
No provider returns are embedded into the public application source.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from .data import parse_chart, digest
from .synthetic import synthetic_prices

ASSETS = ("SPY", "GLD", "IEF", "BIL")


def fetch_planner_data(root):
    root = Path(root)
    raw, processed = root/"data/raw/planner_v3", root/"data/processed/planner_v3"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    manifest_path = raw/"manifest.json"
    if manifest_path.exists():
        return load_planner_data(root)[1]
    frames, entries = {}, []
    for symbol in ASSETS:
        path = raw/f"{symbol}.yahoo.json"
        existing = root/f"data/raw/{symbol}.yahoo.json"
        if existing.exists():
            content = existing.read_bytes()
            origin = "existing local research snapshot"
        elif path.exists():
            content = path.read_bytes()
            origin = "existing planner download"
        else:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            response = requests.get(url, params={"period1": int(pd.Timestamp("2004-12-01", tz="UTC").timestamp()),
                "period2": int(pd.Timestamp("2026-01-01", tz="UTC").timestamp()),
                "interval": "1d", "events": "div,splits"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            content, origin = response.content, response.url
        frame = parse_chart(json.loads(content), symbol).loc["2004-12-31":"2025-12-31"]
        path.write_bytes(content)
        frames[symbol] = frame.adj_close
        proxy = frame.adj_close.pct_change()
        ordinary = (frame.dividend_ex_date_amount == 0) & (frame.split_ratio == 0)
        ordinary_error = float((proxy-frame.close.pct_change())[ordinary].abs().max())
        # Return units use vendor-adjusted history. BIL's 2017 reverse split
        # is already reflected in both historical Close and AdjClose. Applying
        # its action factor again would create a fictitious 50% return.
        split_days = frame.split_ratio.ne(0)
        split_error = float((proxy-frame.close.pct_change())[split_days].abs().max()) if split_days.any() else 0.
        split_returns = proxy[split_days]
        if (ordinary_error > 1e-5 or split_error > 1e-5
                or (split_returns.abs() > .5).any()):
            raise ValueError(f"{symbol}: unhandled return convention/split audit.")
        entries.append({"symbol": symbol, "source": origin, "sha256": digest(path),
                        "ordinary_return_audit_max_difference": ordinary_error,
                        "split_count": int(split_days.sum()), "split_return_audit_max_difference": split_error,
                        "split_convention": "vendor-adjusted return units; no second split adjustment"})
    # BIL has a shorter history. Trim explicitly to the common inception range,
    # then require identical daily calendars rather than filling missing values.
    first = max(frame.index[0] for frame in frames.values())
    last = min(frame.index[-1] for frame in frames.values())
    frames = {name: frame.loc[first:last] for name, frame in frames.items()}
    reference = frames[ASSETS[0]].index
    if any(not frame.index.equals(reference) for frame in frames.values()):
        raise ValueError("Planner asset calendars disagree; do not silently fill missing returns.")
    prices = pd.DataFrame(frames)
    prices = prices/prices.iloc[0]*100
    if len(prices) < 3500 or not np.isfinite(prices.to_numpy()).all():
        raise ValueError("Planner historical coverage is incomplete.")
    output = processed/"return_indices.csv"
    prices.to_csv(output, float_format="%.12g")
    manifest = {"source": "Cached Yahoo adjusted-close total-return proxies; no second-provider validation",
                "assets": list(ASSETS), "created_utc": datetime.now(timezone.utc).isoformat(),
                "first_session": str(prices.index[0].date()), "last_session": str(prices.index[-1].date()),
                "processed_sha256": digest(output), "files": entries,
                "scope": "Educational scenario assumptions, not executable share prices or forecasts"}
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


def load_planner_data(root):
    root = Path(root)
    path, meta = root/"data/processed/planner_v3/return_indices.csv", root/"data/raw/planner_v3/manifest.json"
    manifest = json.loads(meta.read_text())
    if digest(path) != manifest["processed_sha256"]:
        raise ValueError("Planner snapshot hash changed.")
    frame = pd.read_csv(path, index_col="date", parse_dates=True)
    if tuple(frame.columns) != ASSETS:
        raise ValueError("Wrong planner asset order.")
    return frame, manifest


def planner_market(root):
    if (Path(root)/"data/raw/planner_v3/manifest.json").exists():
        prices, manifest = load_planner_data(root)
        return prices, manifest, False
    prices = synthetic_prices().rename(columns={"QQQ": "SPY"})
    prices["BIL"] = 100*np.exp(np.arange(len(prices))*np.log1p(.01)/252)
    return prices, {"source": "SYNTHETIC educational paths; labels are asset-class placeholders, not observed SPY returns",
                    "assets": list(ASSETS), "first_session": str(prices.index[0].date()),
                    "last_session": str(prices.index[-1].date()),
                    "processed_sha256": __import__("hashlib").sha256(prices.to_csv(float_format="%.12g").encode()).hexdigest()}, True


def planner_risky_history(root):
    """Longer risky-only history for causal covariance, without BIL truncation.

    Reuse and verify the exact raw files already hashed in the planner manifest.
    This history only estimates covariance; the scenario/replay universe retains
    the four-asset common calendar used for performance accounting.
    """
    root = Path(root)
    raw = root/'data/raw/planner_v3'
    manifest = json.loads((raw/'manifest.json').read_text())
    entries = {entry['symbol']:entry for entry in manifest['files']}
    frames = {}
    for symbol in ASSETS[:3]:
        path = raw/f'{symbol}.yahoo.json'
        if digest(path) != entries[symbol]['sha256']:
            raise ValueError('Risk-estimation raw snapshot hash changed.')
        frames[symbol] = parse_chart(json.loads(path.read_bytes()),symbol).adj_close.loc['2004-12-31':manifest['last_session']]
    first = max(frame.index[0] for frame in frames.values())
    frames = {name:frame.loc[first:] for name,frame in frames.items()}
    reference = frames['SPY'].index
    if any(not frame.index.equals(reference) for frame in frames.values()):
        raise ValueError('Risk-estimation calendars disagree.')
    prices = pd.DataFrame(frames)
    return prices/prices.iloc[0]*100
