"""Reproducible artificial regime-switching paths for a credential-free demo."""

import numpy as np
import pandas as pd


def synthetic_prices(start="2004-01-01", end="2025-12-31", seed=20261022):
    dates = pd.bdate_range(start, end, name="date")
    rng = np.random.default_rng(seed)
    correlation = np.array([[1., .15, -.2], [.15, 1., .05], [-.2, .05, 1.]])
    normal = rng.standard_t(6, (len(dates), 3))*np.sqrt(4/6)
    correlated = normal@np.linalg.cholesky(correlation).T
    regime, scales = 0, []
    for _ in dates:
        if rng.random() < (.015 if regime == 0 else .06):
            regime = 1-regime
        scales.append(2.5 if regime else .75)
    r = correlated*np.array([.012, .009, .004])*np.asarray(scales)[:, None]
    r += np.array([.00025, .00015, .00008])
    values = 100*np.cumprod(1+np.clip(r, -.85, .85), axis=0)
    return pd.DataFrame(values, index=dates, columns=["QQQ", "GLD", "IEF"])
