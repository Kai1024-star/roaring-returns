"""Frictionless dollar plans. Execution and costs are handled separately."""

import numpy as np

STRATEGIES = ("proportional", "annual", "threshold_center", "cashflow_only", "min_sales_band")


def validate_inputs(holdings, cash, target):
    h, a = np.asarray(holdings, float), np.asarray(target, float)
    if h.ndim != 1 or h.shape != a.shape or len(h) < 2:
        raise ValueError("Holdings and target must be equal-length vectors.")
    if not np.isfinite(h).all() or not np.isfinite(a).all() or not np.isfinite(cash):
        raise ValueError("Inputs must be finite.")
    if np.any(h < 0) or cash < 0 or np.any(a <= 0) or not np.isclose(a.sum(), 1):
        raise ValueError("Nonnegative holdings/cash and positive unit-sum targets required.")
    if h.sum() + cash <= 0:
        raise ValueError("Wealth must be positive.")
    return h, a


def project_box_simplex(target, lower, upper):
    """Euclidean projection onto sum(x)=1 and lower<=x<=upper."""
    a, lo, hi = (np.asarray(x, float) for x in (target, lower, upper))
    if np.any(lo > hi + 1e-12) or lo.sum() > 1 + 1e-10 or hi.sum() < 1 - 1e-10:
        raise ValueError("Infeasible box-simplex.")
    left, right = float(np.min(lo - a)), float(np.max(hi - a))
    for _ in range(65):
        mid = (left + right) / 2
        if np.clip(a + mid, lo, hi).sum() < 1:
            left = mid
        else:
            right = mid
    result = np.clip(a + (left + right) / 2, lo, hi)
    # Absorb floating-point remainder without breaching bounds.
    remainder = 1 - result.sum()
    for i in range(len(result)):
        change = np.clip(remainder, lo[i] - result[i], hi[i] - result[i])
        result[i] += change
        remainder -= change
    return result


def exact_target_cash_required(holdings, target):
    h, a = validate_inputs(holdings, 0, target)
    return float(max(0, np.max(h / a - h.sum())))


def minimum_sale_bound(holdings, cash, lower, upper):
    h = np.asarray(holdings, float)
    lo, hi = np.asarray(lower, float), np.asarray(upper, float)
    if cash < 0 or np.any(h < 0) or np.any(lo < 0) or np.any(hi > 1):
        raise ValueError("Invalid minimum-sale inputs.")
    if np.any(lo > hi) or lo.sum() > 1 + 1e-10 or hi.sum() < 1 - 1e-10:
        raise ValueError("Infeasible band.")
    total = h.sum() + cash
    forced = np.maximum(h - hi * total, 0).sum()
    required = np.maximum(lo * total - h, 0).sum()
    return float(max(forced, required - cash, 0))


def buy_only(holdings, cash, target):
    h, a = validate_inputs(holdings, cash, target)
    total = h.sum() + cash
    return total * project_box_simplex(a, h / total, np.ones(len(h)))


def min_sales_band(holdings, cash, target, band):
    """Minimize sales first, then squared distance to target, analytically.

    At the minimum-sale bound, either only forced upper-cap sales are allowed,
    or only forced lower-floor purchases are allowed. Each case reduces the
    tie-break to one box-simplex projection, avoiding a numerical QP.
    """
    h, a = validate_inputs(holdings, cash, target)
    total = h.sum() + cash
    lo, hi = np.maximum(a - band, 0), np.minimum(a + band, 1)
    forced = np.maximum(h - hi * total, 0).sum()
    required = np.maximum(lo * total - h, 0).sum()
    if forced >= required - cash:
        lo = np.maximum(lo, np.minimum(h / total, hi))
    else:
        hi = np.minimum(hi, np.maximum(h / total, lo))
    return total * project_box_simplex(a, lo, hi)


def plan(strategy, holdings, cash, target, band, execution_month):
    h, a = validate_inputs(holdings, cash, target)
    if strategy not in STRATEGIES or not 0 <= band < 1:
        raise ValueError("Unknown strategy or invalid band.")
    total = h.sum() + cash
    proportional = h + cash * a
    if strategy == "proportional":
        final = proportional
    elif strategy == "annual":
        final = a * total if execution_month == 1 else proportional
    elif strategy == "threshold_center":
        outside = np.max(np.abs(proportional / total - a)) > band + 1e-12
        final = a * total if outside else proportional
    elif strategy == "cashflow_only":
        final = buy_only(h, cash, a)
    else:
        final = min_sales_band(h, cash, a, band)
    trades = final - h
    if strategy in ("proportional", "cashflow_only"):
        trades = np.maximum(trades, 0)  # Remove projection roundoff, never sell in a buy-only rule.
    if abs(trades.sum() - cash) > 1e-7 * total:
        raise ArithmeticError("Plan is not self-financing.")
    return trades
