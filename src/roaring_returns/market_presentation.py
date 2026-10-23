"""Display-only comparisons of existing ledgers; no fitted model or new trades."""
import numpy as np
from .market_models import path_summary, empirical_cvar


def comparison_rows(cal, candidates, results, monthly_returns, initial):
    """Keep path IDs paired; a quantile difference is not a paired difference."""
    reference = results['Feasible equal-weight control']
    rows = []
    for name, weights in candidates.items():
        result = results[name]
        if result.wealth.shape != reference.wealth.shape or not np.array_equal(result.deposits, reference.deposits):
            raise ValueError('A paired comparison requires the same grid and deposits.')
        difference = result.wealth[:, -1] - reference.wealth[:, -1]
        rows.append(dict(name=name, summary=path_summary(result),
            paired=np.quantile(difference, [.05, .5, .95]).tolist(),
            volatility=float(np.sqrt(weights[1:] @ cal.covariance @ weights[1:])),
            monthly_cvar=float(empirical_cvar(-monthly_returns @ weights)),
            monthly_cvar_dollars=float(initial * empirical_cvar(-monthly_returns @ weights)) if initial > 0 else None,
            initial_holdings=result.holdings[0].tolist(),
            initial_fee=float(initial-result.wealth[0,0]),
            weights=list(map(float,weights))))
    return rows
