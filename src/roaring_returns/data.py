"""Public data acquisition with immutable raw snapshots and an audit manifest."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
import requests

ASSETS = ("QQQ", "GLD", "IEF")


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def parse_chart(payload, symbol):
    chart = payload.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"{symbol}: vendor returned an error: {chart.get('error')}")
    result = chart["result"][0]
    if result["meta"].get("currency") != "USD" or result["meta"].get("symbol") != symbol:
        raise ValueError(f"{symbol}: unexpected instrument/currency.")
    dates = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    frame = pd.DataFrame(result["indicators"]["quote"][0])
    frame["adj_close"] = result["indicators"]["adjclose"][0]["adjclose"]
    frame.index = pd.DatetimeIndex(dates.date, name="date")
    frame["dividend_ex_date_amount"] = 0.0
    frame["split_ratio"] = 0.0
    for kind, field in (("dividends", "dividend_ex_date_amount"), ("splits", "split_ratio")):
        for event in result.get("events", {}).get(kind, {}).values():
            date = pd.Timestamp(event["date"], unit="s", tz="UTC").tz_convert("America/New_York").normalize().tz_localize(None)
            if date not in frame.index:
                raise ValueError(f"{symbol}: {kind} event has no matching price session: {date}.")
            frame.loc[date, field] = (event["amount"] if kind == "dividends"
                                      else event["numerator"] / event["denominator"])
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{symbol}: duplicate or unsorted dates.")
    if frame[["open", "close", "adj_close"]].isna().any().any():
        raise ValueError(f"{symbol}: missing prices; refusing silent forward-fill.")
    if not np.isfinite(frame[["close", "adj_close"]].to_numpy()).all() or (frame[["close", "adj_close"]] <= 0).any().any():
        raise ValueError(f"{symbol}: invalid price.")
    return frame


def fetch_data(root, refresh=False):
    root = Path(root)
    raw = root / "data" / "raw"
    processed = root / "data" / "processed"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    frames, entries = {}, []
    start = int(pd.Timestamp("2004-12-01", tz="UTC").timestamp())
    end = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp())
    for symbol in ASSETS:
        path = raw / f"{symbol}.yahoo.json"
        old = next((x for x in previous.get("files", []) if x["symbol"] == symbol), {})
        fetched_at = old.get("fetched_at_utc", "unknown_cached_time")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"period1": start, "period2": end, "interval": "1d", "events": "div,splits"}
        if refresh or not path.exists():
            response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            payload = response.json()
            parse_chart(payload, symbol)  # Validate before replacing an existing snapshot.
            path.write_bytes(response.content)
            fetched_at = datetime.now(timezone.utc).isoformat()
        else:
            payload = json.loads(path.read_bytes())
            if old.get("sha256") and digest(path) != old["sha256"]:
                raise ValueError(f"{symbol}: cached raw snapshot hash changed.")
        frame = parse_chart(payload, symbol)
        frame = frame.loc["2004-12-01":"2025-12-31"]
        frame.to_csv(processed / f"{symbol}_vendor_daily.csv", float_format="%.12g")
        frames[symbol] = frame
        entries.append(dict(symbol=symbol, url=requests.Request("GET", url, params=params).prepare().url,
                            file=str(path.relative_to(root)), sha256=digest(path),
                            fetched_at_utc=fetched_at, first_date=str(frame.index[0].date()),
                            last_date=str(frame.index[-1].date()), rows=len(frame),
                            dividend_events=int((frame.dividend_ex_date_amount != 0).sum()),
                            split_events=int((frame.split_ratio != 0).sum())))
    reference_index = frames[ASSETS[0]].index
    for symbol, frame in frames.items():
        if not frame.index.equals(reference_index):
            raise ValueError(f"{symbol}: trading calendars disagree; audit before combining.")
    combined = pd.DataFrame({s: frames[s].adj_close for s in ASSETS})
    combined = combined.loc["2004-12-31":]
    if len(combined) < 4000 or combined.index[0] > pd.Timestamp("2005-01-03"):
        raise ValueError("Historical coverage unexpectedly short.")
    # Unit levels are arbitrary. Ratios of vendor adjusted closes are the return proxy.
    combined = combined / combined.iloc[0] * 100
    output = processed / "total_return_indices.csv"
    combined.to_csv(output, float_format="%.12g")
    changes = combined.pct_change().iloc[1:]
    audit = {}
    for symbol, frame in frames.items():
        proxy = frame.adj_close.pct_change()
        reconstructed = (frame.close + frame.dividend_ex_date_amount) / frame.close.shift() - 1
        difference = (proxy - reconstructed).abs()
        backadjustment_proxy = frame.close / (frame.close.shift() - frame.dividend_ex_date_amount) - 1
        convention_error = float((proxy - backadjustment_proxy).abs().max())
        ordinary = (frame.dividend_ex_date_amount == 0) & (frame.split_ratio == 0)
        ordinary_error = float(difference[ordinary].max())
        max_error = float(difference.max())
        # These are gross data-error checks, not assertions that two reinvestment
        # conventions are identical or an independent-provider certification.
        if ordinary_error > 1e-5 or max_error > 5e-4 or convention_error > 1e-5 or proxy.abs().max() > .5:
            raise ValueError(f"{symbol}: corporate-action/return audit failed; inspect vendor snapshot.")
        audit[symbol] = dict(max_proxy_vs_reconstructed_difference=max_error,
                             max_vendor_backadjustment_convention_difference=convention_error,
                             max_non_distribution_difference=ordinary_error,
                             note="same-vendor internal consistency only; conventions differ on distribution dates")
    manifest = dict(source="Yahoo Finance public chart endpoint", schema_version=1,
                    purpose="private research; no raw-data redistribution assumed",
                    price_convention="vendor adjusted-close total-return proxy; not historical executable share prices",
                    distribution_convention="implicit reinvestment in original asset; never added as separate cash",
                    pay_dates_available=False, independent_provider_validated=False,
                    internal_return_audit=audit,
                    files=entries, processed_file=str(output.relative_to(root)),
                    processed_sha256=digest(output), common_rows=len(combined),
                    max_absolute_daily_return={k: float(v) for k, v in changes.abs().max().items()},
                    software=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def load_prices(root):
    root = Path(root)
    path = root / "data/processed/total_return_indices.csv"
    manifest = json.loads((root / "data/raw/manifest.json").read_text())
    if digest(path) != manifest["processed_sha256"]:
        raise ValueError("Processed data hash changed; regenerate or audit first.")
    return pd.read_csv(path, index_col="date", parse_dates=True), manifest
