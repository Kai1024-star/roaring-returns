"""Auditable planner views: dollar attribution, return risk, model sensitivity."""
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from .planner import ASSET_NAMES, describe_result
from .planning_models import money_weighted_return, performance_frame, dollar_units


def money(value):
    value = 0. if abs(value)<.005 else value
    amount = f'{abs(value):,.2f}' if abs(value)<100 else f'{abs(value):,.0f}'
    return ('$' if value>=0 else '−$')+amount


def performance_metrics(result, reference=None):
    pnl = float(result.wealth[0, -1]-result.contributed[-1])
    valid = bool(result.return_valid[0, -1])
    cols = st.columns(3)
    cols[0].metric('Net investment gain / loss', money(pnl))
    cols[1].metric('Cumulative return · deposits excluded', f'{result.nav[0, -1]-1:+.2%}' if valid else 'Not yet funded')
    cols[2].metric('Largest return drawdown', f'−{result.max_drawdown[0]:.2%}' if valid else 'Not yet funded')
    st.markdown(f"You put in **{money(result.contributed[-1])}**. Market gains/losses and fees changed that by **{money(pnl)}**, leaving **{money(result.wealth[0,-1])}**. A rising balance can come entirely from deposits.".replace('$',r'\$'))
    if reference is not None:
        delta = result.wealth[0, -1]-reference.wealth[0, -1]
        st.caption(f"Same deposits in the cash proxy: {money(reference.wealth[0,-1])}. Difference from that reference: {money(delta)}. Fees paid: {money(result.fees[0])}. This comparison covers only this replay.".replace('$',r'\$'))
    irr = money_weighted_return(result)
    st.caption('Return excluding deposits is unitized time-weighted return. Drawdown measures a fall in that return index; it can differ substantially from the dollar dip of a growing account.')
    if irr is not None:
        years = ((pd.Timestamp(result.dates[-1])-pd.Timestamp(result.dates[0])).days/365.25
                 if result.period_unit == 'Session' else (result.wealth.shape[1]-1)/12)
        equivalent = np.expm1(np.log1p(irr)*years)
        st.caption(f'Money-weighted equivalent over this same replay: {equivalent:+.2%} (includes cash-flow timing). Both this rate and the time-weighted return above cover the full replay, not one year.')


def attribution(result):
    if result.sample_asset_pnl is None:
        return
    gross = result.sample_asset_pnl[-1]
    rows = [{'Component': 'Deposits', 'Dollars': result.contributed[-1]}]
    rows += [{'Component': name+' market P&L', 'Dollars': gross[i]} for i, name in enumerate(ASSET_NAMES)]
    rows += [{'Component': 'Trading fees', 'Dollars': -result.fees[0]},
             {'Component': 'Ending balance', 'Dollars': result.wealth[0,-1]}]
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, width='stretch', column_config={'Dollars': st.column_config.NumberColumn(format='$%.2f')})
    st.caption('Exact reconciliation: ending balance = deposits + asset market P&L − trading fees. Fund expenses are embedded in the provider returns; taxes are not modeled.')


def future_charts(result, budget, settings, real):
    time = np.arange(budget.months+1)
    scale = (1+settings.inflation)**(time/12) if real else np.ones(len(time))
    unit = "Today's dollars" if real else 'Nominal dollars'
    view = st.radio('What should the scenario chart show?', ['Investment gain / loss', 'Account balance', 'Investment return'], horizontal=True)
    if view == 'Investment gain / loss':
        values = dollar_units(result,settings.inflation,real)['pnl']
        title, base = unit+' · net investment P&L', 0
    elif view == 'Account balance':
        values = result.wealth/scale
        title, base = unit, None
    else:
        values = np.where(result.return_valid, (result.nav-1)*100, np.nan)
        title, base = 'Cumulative nominal return excluding deposits (%)', 0
    q = np.full((3,len(time)),np.nan)
    funded_columns = np.isfinite(values).any(0)
    if funded_columns.any():
        q[:,funded_columns] = np.nanquantile(values[:,funded_columns],[.1,.5,.9],axis=0)
    frame = pd.DataFrame({'Month':time, 'Lower':q[0], 'Middle':q[1], 'Upper':q[2], 'Deposits':dollar_units(result,settings.inflation,real)['deposits']})
    chart = alt.Chart(frame).encode(x=alt.X('Month:Q', title='Months from now'))
    band = chart.mark_area(color='#168a94',opacity=.16).encode(y=alt.Y('Lower:Q',title=title,scale=alt.Scale(zero=True)),y2='Upper:Q')
    mid = chart.mark_line(color='#168a94',strokeWidth=2.5).encode(y='Middle:Q',tooltip=['Month',alt.Tooltip('Lower:Q',format=',.2f'),alt.Tooltip('Middle:Q',format=',.2f'),alt.Tooltip('Upper:Q',format=',.2f')])
    layers = band+mid
    if view == 'Account balance':
        layers += chart.mark_line(color='#8d9dad',strokeDash=[5,4]).encode(y='Deposits:Q')
        if budget.goal_today > 0:
            frame['Goal'] = budget.goal_today if real else budget.goal_today*(1+settings.inflation)**(time/12)
            goal = alt.Chart(frame).mark_line(color='#bd963f',strokeDash=[3,4]).encode(x='Month:Q',y='Goal:Q')
            layers += goal
    if base is not None:
        layers += alt.Chart(pd.DataFrame({'Zero':[base]})).mark_rule(color='#8d9dad',strokeDash=[4,4]).encode(y='Zero:Q')
    st.altair_chart(layers.properties(height=285),width='stretch')
    st.caption('Shading: pointwise 10th–90th percentiles; line: pointwise median. These are scenario summaries, not one path or a coverage guarantee. Percentage returns stay nominal; the purchasing-power switch changes dollar views. Investment P&L subtracts every deposit and includes trading fees. In today’s dollars, each deposit is discounted at its own date; P&L includes inflation erosion.')
    active = result.return_valid[:,-1]
    if active.any():
        dd = pd.DataFrame({'Maximum return drawdown (%)':result.max_drawdown[active]*100})
        plot = alt.Chart(dd).mark_bar(color='#b66556').encode(x=alt.X('Maximum return drawdown (%):Q',bin=alt.Bin(maxbins=24)),y=alt.Y('count()',title='Scenario count'),tooltip=['count()'])
        st.altair_chart(plot.properties(height=150),width='stretch')
        st.caption('Drawdowns are measured at daily closes within each resampled month. The input sample still contains limited market history; repeated draws are not independent evidence.')
    else:
        st.info('No money reaches the investment pot in this horizon. Investment returns and drawdowns are unavailable.')


def scenario_row(label, result, budget, settings):
    stats = describe_result(result,budget,settings)
    return {'Case':label, 'Lower ending ($ today)':stats['ending_low_today'],
            'Middle ending ($ today)':stats['ending_middle_today'], 'Upper ending ($ today)':stats['ending_high_today'],
            'Median net P&L ($ nominal)':stats['median_net_pnl'], 'Median cumulative return':stats['median_twr'],
            '90th-percentile drawdown':stats['drawdown_90'], 'Ends below deposits (nominal)':stats['ending_below_deposits_frequency'],
            'Daily dollar dip crosses your line':stats['dip_exceeds_comfort_frequency'], 'Median fees ($)':stats['median_fees'],
            'Median selling months':stats['median_selling_months']}


def show_comparison(rows):
    table = pd.DataFrame(rows)
    st.dataframe(table,hide_index=True,width='stretch',column_config={
        **{n:st.column_config.NumberColumn(format='$%.0f') for n in table if '($' in n},
        **{n:st.column_config.NumberColumn(format='percent') for n in table if n in ['Median cumulative return','90th-percentile drawdown','Ends below deposits (nominal)','Daily dollar dip crosses your line']}})
