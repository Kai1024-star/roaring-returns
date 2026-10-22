"""Re-render prose/count thresholds without changing any simulated path.

The original run manifest remains intact. A separate presentation manifest
identifies this renderer and makes the post-run annotation explicit.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import pandas as pd
from roaring_returns.data import digest
from roaring_returns.research_runner import _write_report

root = Path(__file__).resolve().parents[1]
for name in ("execution_v2", "execution_v2_synthetic"):
    folder = root/"results"/name
    manifest = json.loads((folder/"manifest.json").read_text())
    protocol = json.loads((folder/"protocol.json").read_text())
    for path, expected in manifest["numerical_source_hashes"].items():
        if digest(root/path) != expected:
            raise ValueError(f"Refusing presentation refresh: numerical source changed {path}")
    _write_report(folder, pd.read_csv(folder/"summary.csv"), protocol, manifest)
    presentation = {"created_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Post-run reporting update only: explicit negative ML findings, material-sale reporting threshold, solver counts and rendered figure. Numerical paths, summary and monthly outcomes were not altered.",
        "renderer_sha256": digest(root/"src/roaring_returns/research_runner.py"),
        "script_sha256": digest(Path(__file__)),
        "sale_count_threshold_fraction_signal_wealth": 1e-6}
    (folder/"presentation_manifest.json").write_text(json.dumps(presentation, indent=2)+"\n")
    hashes = {p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name != "artifact_hashes.json"}
    (folder/"artifact_hashes.json").write_text(json.dumps(hashes, indent=2)+"\n")
    print(f"Refreshed presentation only: {folder}")
