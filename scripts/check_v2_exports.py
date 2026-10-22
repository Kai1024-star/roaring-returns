"""Offline verification of public derived artifacts and numerical provenance."""
from pathlib import Path
from hashlib import sha256
import json
import numpy as np
import pandas as pd


def verify(folder, root):
    folder, root = Path(folder), Path(root)
    digest = lambda p: sha256(p.read_bytes()).hexdigest()
    hashes = json.loads((folder/"artifact_hashes.json").read_text())
    for name, expected in hashes.items():
        if digest(folder/name) != expected:
            raise ValueError(f"Artifact hash mismatch: {folder/name}")
    manifest = json.loads((folder/"manifest.json").read_text())
    if digest(root/"configs/execution_v2.json") != manifest["protocol_sha256"]:
        raise ValueError("Protocol changed since the published run.")
    for name, expected in manifest["numerical_source_hashes"].items():
        if digest(root/name) != expected:
            raise ValueError(f"Numerical source changed: {name}")
    summary = pd.read_csv(folder/"summary.csv")
    monthly = pd.read_csv(folder/"monthly_metrics.csv")
    curves = pd.read_csv(folder/"monthly_curves.csv")
    if len(summary) != manifest["configurations"] or summary.duplicated(["period", "strategy"]).any():
        raise ValueError("Missing or duplicate study configurations.")
    if not np.isfinite(curves.nav).all() or (curves.nav <= 0).any():
        raise ValueError("Invalid published NAV.")
    for row in summary.itertuples():
        events = monthly[(monthly.period == row.period) & (monthly.strategy == row.strategy)]
        if (len(events) != row.months or events.posttrade_outside_band.sum() != row.violating_months
                or not np.isclose(np.sqrt(np.mean(events.posttrade_rms_deviation_pp**2)), row.posttrade_rms_deviation_pp)
                or not np.isclose(12*events.actual_sales_fraction_signal.mean(), row.annual_sales_over_signal_wealth)):
            raise ValueError(f"Monthly/summary mismatch: {row.period}/{row.strategy}")
    return {"folder": folder.name, "configurations": len(summary), "artifact_hashes": len(hashes),
            "numerical_modules": len(manifest["numerical_source_hashes"]),
            "lp_only_months": int(summary.tie_break_incomplete_months.sum()),
            "solver_retries": int(summary.solver_retry_months.sum())}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps([verify(root/"results"/name, root) for name in
                      ("execution_v2", "execution_v2_synthetic")], indent=2))
