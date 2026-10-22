"""Joint whole-month blocks with within-month daily valuation.

Blocks never wrap across the end of a snapshot. Repeated paths do not create
independent market samples. Scenario assumptions share exact month selections.
"""
from dataclasses import dataclass
import numpy as np
from .planner import PlanningResult, _settle_month, flow_neutral_step, monthly_returns

SCENARIOS = ('Historical excess returns', 'Lower excess returns', 'Zero average excess returns')


@dataclass(frozen=True)
class MonthLibrary:
    log_returns: np.ndarray
    counts: np.ndarray
    dates: np.ndarray
    monthly_logs: np.ndarray
    labels: tuple


def month_library(prices, recent_months=None):
    monthly_returns(prices)
    if prices.shape[1] != 4:
        raise ValueError('Daily scenarios require stock, gold, bond and cash-proxy columns.')
    daily = np.log(prices/prices.shift()).iloc[1:]
    # Discard the initial partial calendar month; its final close is the base.
    daily = daily.loc[daily.index.to_period('M') > prices.index[0].to_period('M')]
    groups = list(daily.groupby(daily.index.to_period('M')))
    if recent_months is not None:
        groups = groups[-recent_months:]
    if len(groups) < 24:
        raise ValueError('At least 24 full historical months are required.')
    width = max(len(group) for _, group in groups)
    logs = np.zeros((len(groups), width, 4))
    counts = np.zeros(len(groups), int)
    dates = np.full((len(groups), width), '', dtype='U10')
    for i, (_, frame) in enumerate(groups):
        n = len(frame); counts[i] = n
        logs[i, :n] = frame.to_numpy()
        dates[i, :n] = frame.index.strftime('%Y-%m-%d')
    return MonthLibrary(logs, counts, dates, logs.sum(1), tuple(str(label) for label, _ in groups))


def sampled_months(library, months, settings):
    settings.validate()
    if not 1 <= months <= 120 or len(library.counts) < settings.block_months:
        raise ValueError('Invalid horizon or block longer than the input sample.')
    rng = np.random.default_rng(settings.seed)
    # Full 120-month draw layout preserves a horizon's prefixes.
    starts = rng.integers(0, len(library.counts)-settings.block_months+1,
                         (settings.paths, int(np.ceil(120/settings.block_months))))
    return (starts[:, :, None]+np.arange(settings.block_months)).reshape(settings.paths, -1)[:, :months]


def zero_premium_center(library, block_months, position):
    """Exact conditional mean for uniform non-wrapping block starts.

    Boundary months have unequal selection probability. At block offset j the
    eligible source months are j ... j+N-block, each equally probable. Center
    that distribution, rather than the uniformly weighted whole library. This
    preserves horizon prefixes and zero expected log premium at every position.
    """
    offset = position % block_months
    count = len(library.counts)-block_months+1
    excess = library.monthly_logs[:, :3]-library.monthly_logs[:, 3:4]
    return excess[offset:offset+count].mean(0)


def anchored_month(library, indexes, settings, assumption, zero_excess_mean=None):
    """Preserve observed daily shapes, adjust monthly log means exactly.

    Add the same daily shift to BIL and risky returns so the cash proxy compounds
    to the cash assumption at the month end. This retains BIL's weekday pattern.
    Lower = subtract 2 log pp/year. Zero = remove the input sample's per-asset
    mean monthly excess log return; it does not impose zero arithmetic return.
    """
    if assumption not in SCENARIOS:
        raise ValueError('Unknown scenario assumption.')
    raw = library.log_returns[indexes].copy()
    n = library.counts[indexes]
    mask = np.arange(raw.shape[1])[None, :] < n[:, None]
    cash_shift = (np.log1p(settings.cash_rate)/12-library.monthly_logs[indexes, 3])/n
    raw += cash_shift[:, None, None]*mask[:, :, None]
    adjustment = np.full(3, settings.return_haircut/12)
    if assumption == 'Lower excess returns':
        adjustment += .02/12
    elif assumption == 'Zero average excess returns':
        adjustment += ((library.monthly_logs[:, :3]-library.monthly_logs[:, 3:4]).mean(0)
                       if zero_excess_mean is None else zero_excess_mean)
    raw[:, :, :3] -= adjustment[None, None, :]/n[:, None, None]*mask[:, :, None]
    return raw, n


def simulate_daily_scenarios(library, budget, weights, settings, assumption=SCENARIOS[0], indexes=None):
    """Monthly endpoint distributions, daily risk, and one auditable daily path."""
    budget.validate(); settings.validate()
    a = np.asarray(weights, float)
    if a.shape != (4,) or not np.isfinite(a).all() or (a < 0).any() or not np.isclose(a.sum(), 1):
        raise ValueError('Long-only allocation weights must sum to one.')
    indexes = sampled_months(library, budget.months, settings) if indexes is None else np.asarray(indexes)
    if indexes.shape != (settings.paths, budget.months) or (indexes < 0).any() or (indexes >= len(library.counts)).any():
        raise ValueError('Wrong common scenario selections.')
    count, months = indexes.shape
    rate = settings.cost_bps/10000
    initial = budget.initial/(1+rate*(1-a[0]))
    h = np.tile(initial*a, (count, 1))
    wealth = np.zeros((count, months+1)); wealth[:, 0] = initial
    nav = np.ones_like(wealth); nav[:, 0] = initial/budget.initial if budget.initial else 1.
    valid = np.zeros_like(wealth, dtype=bool); valid[:, 0] = budget.initial > 0
    fees = np.full(count, budget.initial-initial); fee_path = np.zeros_like(wealth); fee_path[:, 0] = fees
    sales, selling = np.zeros(count), np.zeros(count, int)
    high = np.full(count, budget.initial); dip = np.full(count, budget.initial-initial)
    nav_now = nav[:, 0].copy(); peak = np.ones(count); valid_now = valid[:, 0].copy()
    max_dd = np.where(valid_now, 1-nav_now, 0.)
    dd_path = np.zeros_like(wealth); dd_path[:, 0] = max_dd
    sample = [h[0].copy()]; daily_wealth = [initial]; daily_nav = [nav_now[0]]; daily_valid = [valid_now[0]]
    daily_dd = [max_dd[0]]
    daily_fees = [fees[0]]; daily_deposits = [budget.initial]; daily_assets = [np.zeros(4)]
    source_dates = ['Start']; elapsed_months = [0.]
    month_sample = np.zeros((months+1, 4)); month_sample[0] = h[0]
    month_assets = np.zeros((months+1, 4)); asset_pnl = np.zeros((count, 4))
    flows = budget.contributions()
    for month, flow in enumerate(flows):
        center = zero_premium_center(library, settings.block_months, month)
        logs, lengths = anchored_month(library, indexes[:, month], settings, assumption, center)
        sold_month = np.zeros(count)
        for day in range(int(lengths.max())):
            previous = h.sum(1)
            factors = np.expm1(logs[:, day])
            # Library order stocks/gold/bonds/BIL; holdings order cash/risks.
            gains = h*factors[:, [3, 0, 1, 2]]
            h += gains; asset_pnl += gains
            marked = h.sum(1)
            high = np.maximum(high, marked)
            dip = np.maximum(dip, high-marked)
            finish = day == lengths-1
            paid, sold, new_flow = np.zeros(count), np.zeros(count), np.zeros(count)
            if finish.any():
                h[finish], paid[finish], sold[finish] = _settle_month(h[finish], flow, a, settings)
                new_flow[finish] = flow
            end = h.sum(1)
            fees += paid; sales += sold; sold_month += sold
            nav_now, peak, valid_now, dd = flow_neutral_step(previous, marked, end, new_flow, nav_now, peak, valid_now)
            max_dd = np.maximum(max_dd, dd)
            high = np.maximum(high+new_flow, end); dip = np.maximum(dip, high-end)
            if day < lengths[0]:
                daily_wealth.append(end[0]); sample.append(h[0].copy()); daily_nav.append(nav_now[0]); daily_valid.append(valid_now[0])
                daily_dd.append(dd[0])
                daily_fees.append(fees[0]); daily_deposits.append(daily_deposits[-1]+new_flow[0]); daily_assets.append(asset_pnl[0].copy())
                source_dates.append(f'Month {month+1} · source {library.dates[indexes[0, month], day]}')
                elapsed_months.append(month+(day+1)/lengths[0])
        selling += sold_month > 1e-6*np.maximum(wealth[:, month], 1.)
        wealth[:, month+1] = h.sum(1); nav[:, month+1] = nav_now; valid[:, month+1] = valid_now
        dd_path[:, month+1] = dd
        fee_path[:, month+1] = fees; month_sample[month+1] = h[0]; month_assets[month+1] = asset_pnl[0]
    contributed = budget.initial+np.r_[0., flows.cumsum()]
    if not np.allclose(wealth[:, -1]-contributed[-1], asset_pnl.sum(1)-fees, atol=1e-6, rtol=1e-9):
        raise ArithmeticError('Deposits, market gains, fees and final wealth do not reconcile.')
    illustrative = PlanningResult(np.array([daily_wealth]), fees[:1], sales[:1], selling[:1], dip[:1], np.array(daily_deposits),
        np.array(sample), 'Session', source_dates, nav=np.array([daily_nav]), return_valid=np.array([daily_valid]),
        max_drawdown=max_dd[:1], fee_path=np.array([daily_fees]), sample_asset_pnl=np.array(daily_assets),
        risk_observation='Resampled daily close', elapsed_months=np.array(elapsed_months), drawdown_path=np.array([daily_dd]))
    return PlanningResult(wealth, fees, sales, selling, dip, contributed, month_sample,
        nav=nav, return_valid=valid, max_drawdown=max_dd, fee_path=fee_path,
        sample_asset_pnl=month_assets, sample_path=illustrative, risk_observation='Resampled daily close', drawdown_path=dd_path)
