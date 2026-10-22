"""Static mechanism checks only; no market data or historical backtest.

Requires the locally available NumPy/SciPy. Compare an analytic minimum-sale
formula with a separately formulated linear program, using normalized dollars.
"""

from random import Random
import numpy as np
from scipy.optimize import linprog


def minimum_sales(holdings, contribution, lower, upper):
    total = sum(holdings) + contribution
    forced_sales = sum(max(h - u * total, 0) for h, u in zip(holdings, upper))
    lower_purchases = sum(max(l * total - h, 0) for h, l in zip(holdings, lower))
    return max(forced_sales, lower_purchases - contribution, 0)


def linear_program_sales(holdings, contribution, lower, upper):
    h = np.asarray(holdings, dtype=float)
    n = len(h)
    total = h.sum() + contribution
    net_buys = np.concatenate((np.eye(n), -np.eye(n)), axis=1)
    result = linprog(
        c=[0.0] * n + [1.0] * n,
        A_ub=np.concatenate((net_buys, -net_buys), axis=0),
        b_ub=np.concatenate((np.asarray(upper) * total - h,
                             h - np.asarray(lower) * total)),
        A_eq=[[1.0] * n + [-1.0] * n],
        b_eq=[contribution],
        bounds=[(0, None)] * n + [(0, float(value)) for value in h],
        method="highs",
    )
    if not result.success:
        raise AssertionError(result.message)
    return float(result.fun)


def simplex(rng, n):
    raw = [rng.random() + 0.001 for _ in range(n)]
    return [value / sum(raw) for value in raw]


def main():
    rng = Random(20261022)
    checked = 0
    worst_error = 0.0
    for n in range(2, 7):
        for iteration in range(400):
            holdings = simplex(rng, n)
            target = simplex(rng, n)
            if iteration % 10 == 0:
                lower = target[:]
                upper = target[:]
            else:
                lower = [a * rng.random() for a in target]
                upper = [a + (1 - a) * rng.random() for a in target]
            contribution = 0 if iteration % 7 == 0 else rng.random() * 2
            analytic = minimum_sales(holdings, contribution, lower, upper)
            lp = linear_program_sales(holdings, contribution, lower, upper)
            error = abs(analytic - lp)
            worst_error = max(worst_error, error)
            assert error < 1e-7, (holdings, contribution, lower, upper, analytic, lp)
            checked += 1

    # The upper caps alone do not imply that a no-sale rebalance is possible.
    h, lower, upper = [0.7, 0.3, 0], [0.45, 0.05, 0.05], [0.75, 0.35, 0.35]
    assert abs(minimum_sales(h, 0, lower, upper) - 0.05) < 1e-12
    assert abs(linear_program_sales(h, 0, lower, upper) - 0.05) < 1e-12
    checked += 1

    # Exact target, dollars: $100 new cash still requires a $10 sale.
    h, target = [450, 250, 300], [0.4, 0.3, 0.3]
    c_min = max(0, max(value / weight - sum(h) for value, weight in zip(h, target)))
    assert abs(c_min - 125) < 1e-10
    assert abs(minimum_sales(h, 100, target, target) - 10) < 1e-10
    assert abs(minimum_sales(h, 125, target, target)) < 1e-10
    checked += 3
    print(f"PASS: {checked} static checks; 2001 independent LP comparisons.")
    print(f"Maximum normalized-dollar LP discrepancy: {worst_error:.3g}")
    print("Example: exact-target C_min=$125; with C=$100, minimum sales=$10.")
    print("No historical performance, return improvement, or novelty claim is tested.")


if __name__ == "__main__":
    main()
