"""Causal execution-risk estimates; no expected-return or alpha forecasts.

Ridge uses log lagged realized variances as features and NEXT session's squared
return as its target. Only labels already observed at the forecast origin enter
training. Correlations are shrunk EWMA estimates, not learned return signals.
"""

from dataclasses import dataclass, field
import numpy as np

RISK_MODELS = ("historical", "ewma", "ridge_vol")


@dataclass(frozen=True)
class RiskForecast:
    covariance: np.ndarray
    requested_model: str
    used_model: str
    observations: int
    training_samples: int = 0
    coefficients: np.ndarray | None = None
    diagnostics: dict = field(default_factory=dict)

    @property
    def volatility(self):
        return np.sqrt(np.diag(self.covariance))


def _returns(values):
    x = np.asarray(values, float)
    if x.ndim != 2 or x.shape[1] < 2 or not np.isfinite(x).all() or np.any(x <= -1):
        raise ValueError("Complete simple-return matrix (> -1) required.")
    return x


def shrink_covariance(returns, half_life=None, shrinkage=.15):
    x = _returns(returns)
    if not 0 <= shrinkage <= 1 or (half_life is not None and half_life <= 0):
        raise ValueError("Invalid covariance settings.")
    n = x.shape[1]
    if len(x) < 2:
        return np.eye(n) * .01**2
    w = (np.ones(len(x)) if half_life is None
         else np.exp2((np.arange(len(x))-len(x)+1)/half_life))
    w /= w.sum()
    centered = x - w @ x
    covariance = (centered * w[:, None]).T @ centered
    covariance = (1-shrinkage)*covariance + shrinkage*np.diag(np.diag(covariance))
    covariance += np.eye(n)*1e-10
    return covariance


def _features(squared):
    """At row t all three columns use data through and including t."""
    cumulative = np.vstack([np.zeros((1, squared.shape[1])), np.cumsum(squared, axis=0)])
    result = []
    for window in (1, 5, 22):
        values = np.full_like(squared, np.nan)
        values[window-1:] = (cumulative[window:]-cumulative[:-window])/window
        result.append(np.log(np.maximum(values, 1e-10)))
    return np.stack(result, axis=2)


def forecast_risk(returns, model="ewma", *, lookback=252, training_window=504,
                  minimum_training=126, ridge_penalty=10., half_life=21., shrinkage=.15):
    x = _returns(returns)
    if model not in RISK_MODELS or lookback < 22 or training_window < 1 or minimum_training < 1 or ridge_penalty <= 0:
        raise ValueError("Invalid forecasting configuration.")
    recent = x[-lookback:]
    covariance = shrink_covariance(recent, None if model == "historical" else half_life, shrinkage)
    if model != "ridge_vol":
        return RiskForecast(covariance, model, model, len(x))
    # Retain context for rolling features before the training window.
    history = x[-(training_window+23):]
    features = _features(history**2)
    # X[t] predicts r[t+1]^2. Exclude X[-1] from training: its label is unknown.
    valid = np.isfinite(features[:-1]).all(axis=(1, 2))
    train_x = features[:-1][valid][-training_window:]
    train_y = (history[1:]**2)[valid][-training_window:]
    if len(train_x) < minimum_training:
        return RiskForecast(covariance, model, "ewma_fallback", len(x), len(train_x),
                            diagnostics={"reason": "insufficient matured one-session labels"})
    coefficients, predicted, clip_counts = [], [], 0
    reference = np.maximum(np.diag(covariance), 1e-10)
    for asset in range(x.shape[1]):
        raw = train_x[:, asset, :]
        mean, scale = raw.mean(axis=0), np.maximum(raw.std(axis=0), 1e-6)
        design = np.column_stack([np.ones(len(raw)), (raw-mean)/scale])
        # Scaling the response makes the penalty's interpretation independent of
        # the return unit. The intercept is unpenalized.
        y_scale = max(float(train_y[:, asset].mean()), 1e-10)
        penalty = np.diag([0., ridge_penalty, ridge_penalty, ridge_penalty])
        beta = np.linalg.solve(design.T@design+penalty, design.T@(train_y[:, asset]/y_scale))
        last = np.r_[1., (features[-1, asset]-mean)/scale]
        variance = float(last@beta)*y_scale
        clipped = float(np.clip(variance, .1*reference[asset], 10*reference[asset]))
        clip_counts += int(abs(clipped-variance) > 1e-14)
        coefficients.append(beta)
        predicted.append(clipped)
    old_std = np.sqrt(np.diag(covariance))
    correlation = covariance/np.outer(old_std, old_std)
    new_std = np.sqrt(predicted)
    covariance = correlation*np.outer(new_std, new_std)
    return RiskForecast(covariance, model, model, len(x), len(train_x),
                        np.asarray(coefficients), {"variance_clips": clip_counts,
                        "target": "next-session squared simple return",
                        "features": "log realized variance over 1, 5, 22 sessions"})


def execution_scenarios(returns, forecast, *, count=252, seed=20261022,
                        stress_multiplier=1., include_stress=False, half_life=21.,
                        shrinkage=.15, residual_window=252):
    """Causally filtered joint historical residuals, recolored at the origin.

    Each historical return is standardized by an EWMA estimate available BEFORE
    that return. By default use every one of the latest 252 available residuals;
    there is no random subsample or artificial probability mass for stress cases.
    Optional eigenvector shocks are for explicitly separate stress experiments.
    Finite-scenario CVaR is not a future-market probability guarantee.
    """
    x = _returns(returns)[-(residual_window+126):]
    if (count < 1 or stress_multiplier <= 0 or not np.isfinite(stress_multiplier)
            or not np.isfinite(half_life) or half_life <= 0 or not 0 <= shrinkage <= 1
            or residual_window < 1):
        raise ValueError("Invalid scenario settings.")
    n = forecast.covariance.shape[0]
    if x.shape[1] != n:
        raise ValueError("Forecast and return dimensions disagree.")
    if len(x) >= 23:
        average = x[:22].mean(axis=0)
        covariance = shrink_covariance(x[:22], shrinkage=0)
        decay = np.exp2(-1/half_life)
        residuals = []
        for observation in x[22:]:
            estimate = (1-shrinkage)*covariance+shrinkage*np.diag(np.diag(covariance))+np.eye(n)*1e-10
            residuals.append(np.linalg.solve(np.linalg.cholesky(estimate), observation-average))
            centered = observation-average
            covariance = decay*covariance+(1-decay)*np.outer(centered, centered)
            average = decay*average+(1-decay)*observation
        residuals = np.asarray(residuals)[-residual_window:]
        if count >= len(residuals):
            sampled = residuals
        else:
            rng = np.random.default_rng(seed)
            sampled = residuals[rng.choice(len(residuals), count, replace=False)]
        # Center the historical residual distribution at the signal date. All
        # inputs remain observed history; no expected-return forecast is added.
        sampled = sampled-sampled.mean(axis=0)
        scenarios = sampled @ np.linalg.cholesky(forecast.covariance).T
    elif len(x) >= 2:
        base = shrink_covariance(x, shrinkage=.15)
        residuals = np.linalg.solve(np.linalg.cholesky(base), (x-x.mean(axis=0)).T).T
        scenarios = residuals@np.linalg.cholesky(forecast.covariance).T
    else:
        scenarios = np.zeros((1, n))
    pieces = [scenarios]
    if include_stress:
        eigenvalues, vectors = np.linalg.eigh(forecast.covariance)
        directions = (vectors*np.sqrt(np.maximum(eigenvalues, 0))*3).T
        pieces.extend([directions, -directions])
    return np.clip(np.vstack(pieces)*stress_multiplier, -.5, .5)


def qlike(realized_returns, predicted_variances):
    """Variance QLIKE, scored on matured next-session outcomes only."""
    r, v = np.asarray(realized_returns, float), np.asarray(predicted_variances, float)
    if r.shape != v.shape or not np.isfinite(r).all() or not np.isfinite(v).all() or np.any(v <= 0):
        raise ValueError("Finite matching returns and strictly positive variances required.")
    return np.log(v)+r*r/v
