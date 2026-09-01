import pandas as pd
import json
import os
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_float(v):
    try:
        f = float(v)
        return round(f, 6) if not (np.isnan(f) or np.isinf(f)) else 0.0
    except:
        return 0.0

def dd_recovery_months(equity):
    """Months to recover FROM the deepest drawdown: from its trough back up to
    the prior peak. Returns (months, ongoing). If the equity curve has not yet
    regained the peak, ongoing=True and months = months elapsed since the trough."""
    eq = pd.Series(equity).reset_index(drop=True)
    if len(eq) == 0:
        return 0, False
    run_peak = eq.cummax()
    dd = eq / run_peak - 1
    trough_i = int(dd.idxmin())
    peak_val = float(run_peak.iloc[trough_i])          # the high we must climb back to
    after = eq.iloc[trough_i:]
    hit = after[after >= peak_val]
    if len(hit):
        return int(hit.index[0] - trough_i), False     # trough -> recovered
    return int(len(eq) - 1 - trough_i), True            # still under water


def compute_metrics(returns_series, bench_series, rf_annual=0.06):
    """Compute full institutional metrics for a return series."""
    r = pd.Series(returns_series).dropna()
    b = pd.Series(bench_series).dropna()
    if len(r) == 0:
        return {}
    n = len(r)
    # Cumulative equity
    equity = (1 + r).cumprod()
    cagr = float(equity.iloc[-1]) ** (12 / n) - 1
    vol = r.std() * np.sqrt(12)
    sharpe = (cagr - rf_annual) / vol if vol > 0 else 0
    mdd = float((equity / equity.cummax() - 1).min())
    # DD recovery: months to recover FROM the deepest drawdown, i.e. from the
    # trough (bottom of the max drawdown) back up to the prior peak. If the curve
    # has not regained that peak yet, it is still recovering -> ongoing=True and
    # the count is months-since-trough so far.
    recovery, recovery_ongoing = dd_recovery_months(equity)
    downside = r[r < 0].std() * np.sqrt(12)
    sortino = (cagr - rf_annual) / downside if downside > 0 else 0
    calmar = cagr / abs(mdd) if mdd != 0 else 0
    wins = (r > 0).sum()
    win_rate = wins / n
    avg_gain = float(r[r > 0].mean()) if wins > 0 else 0
    avg_loss = float(r[r < 0].mean()) if (r < 0).sum() > 0 else 0
    
    # Alpha vs bench
    common = r.index.intersection(b.index)
    alpha = (cagr - b.loc[common].mean() * 12) if len(common) > 0 else 0

    return {
        "CAGR": round(cagr * 100, 2),
        "Volatility": round(vol * 100, 2),
        "Sharpe": round(sharpe, 2),
        "Sortino": round(sortino, 2),
        "Calmar": round(calmar, 2),
        "Max_DD": round(mdd * 100, 2),
        "Recovery_Months": recovery,
        "Recovery_Ongoing": recovery_ongoing,
        "Win_Rate": round(win_rate * 100, 1),
        "Avg_Gain": round(avg_gain * 100, 2),
        "Avg_Loss": round(avg_loss * 100, 2),
        "Alpha": round(alpha * 100, 2),
        "Total_Return": round((float(equity.iloc[-1]) - 1) * 100, 2)
    }

def get_equity_curves(df_sum):
    """Build cumulative equity curves for ALL 7 layers + benchmark."""
    layers = ['Base', 'ST', 'EMA', 'COMBO', 'ULTRA', 'COMBO_HEDGE', 'ULTRA_HEDGE', 'Bench']
    equities = {l: [1.0] for l in layers}
    months = []

    for _, row in df_sum.iterrows():
        months.append(str(row['Month']))
        for l in layers:
            col = l if l != 'Bench' else 'Bench'
            equities[l].append(round(equities[l][-1] * (1 + safe_float(row[col])), 4))

    # Remove seed 1.0 and align with months
    return {
        "months": months,
        **{l: equities[l][1:] for l in layers}
    }

def get_heatmap_data(df_sum, layer_col):
    """Build year x month heatmap matrix for a given layer."""
    df = df_sum[['Month', layer_col]].copy()
    df['Date'] = pd.to_datetime(df['Month'])
    df['Year'] = df['Date'].dt.year
    df['MonthNum'] = df['Date'].dt.month
    pivot = df.pivot(index='Year', columns='MonthNum', values=layer_col)
    pivot = pivot.round(4)

    months_short = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    result = []
    for year in pivot.index:
        row = {'year': int(year)}
        for m in range(1, 13):
            val = pivot.at[year, m] if m in pivot.columns else None
            row[months_short[m-1]] = round(float(val)*100, 2) if val is not None and not np.isnan(val) else None
        result.append(row)
    return result

def get_current_portfolio(xl, sector_map):
    """Get the current live portfolio with sector mapping.
    
    Picks the LIVE_PERF_ sheet whose suffix matches the current calendar month
    (YYYY-MM).  If none matches (e.g. month just rolled), falls back to the
    most recent Port_ sheet so the dashboard never shows a future portfolio.
    """
    sheets = xl.sheet_names
    live_sheets = [s for s in sheets if s.startswith('LIVE_PERF_')]
    port_sheets = [s for s in sheets if s.startswith('Port_')]

    # Show the MOST RECENT live sheet. At month-end the engine writes NEXT
    # month's basket (LIVE_MONTH = last completed month + 1), so the live
    # portfolio shows the upcoming month's picks.
    live_sorted = sorted(live_sheets, key=lambda s: s.replace('LIVE_PERF_', ''))
    current_live = live_sorted[-1] if live_sorted else None

    # Sort the Port_ fallback by month rather than trusting workbook sheet
    # order. som_hedge.py writes no LIVE_PERF_ sheet at all (that step lived in
    # update_sqe.py, which is gone), so this fallback is now the normal path,
    # not the rare one -- Port_<signal month> IS the book traded the month
    # after, which is exactly the basket the dashboard should show.
    port_sorted = sorted(port_sheets, key=lambda s: s.replace('Port_', ''))
    target_sheet = current_live if current_live else (port_sorted[-1] if port_sorted else None)
    if not target_sheet:
        return []

    df = pd.read_excel(xl, sheet_name=target_sheet, header=None)
    # Find header row
    header_row = -1
    for i in range(len(df)):
        if str(df.iloc[i, 0]).strip() == 'Stock':
            header_row = i
            break
    if header_row == -1:
        return []

    cols = list(df.iloc[header_row])
    data = df.iloc[header_row+1:].copy()
    data.columns = range(len(data.columns))

    stocks = []
    beta_col = next((j for j, c in enumerate(cols) if c == 'Beta'), None)
    erb_col = next((j for j, c in enumerate(cols) if c == 'ERB'), None)
    wt_col = next((j for j, c in enumerate(cols) if c == 'SIM Weight'), None)
    action_col = next((j for j, c in enumerate(cols) if c == 'Action'), None)
    status_col = next((j for j, c in enumerate(cols) if c == 'Status'), None)
    qty_col = next((j for j, c in enumerate(cols) if c == 'Qty'), None)
    prev_col = next((j for j, c in enumerate(cols) if c == 'Prev_Qty'), None)

    for k in range(len(data)):
        sym = str(data.iloc[k, 0])
        if sym in ('nan', '', 'None') or 'Total' in sym:
            continue
        clean_sym = sym.split('_')[0]
        sector = sector_map.get(clean_sym, 'Other')
        status_val = str(data.iloc[k, status_col]).strip() if status_col is not None else ''
        weight_val = safe_float(data.iloc[k, wt_col]) if wt_col is not None else 0

        # Skip removed/exited stocks — they have Status="Removed" and Weight=0
        if status_val == 'Removed' or weight_val == 0:
            continue

        stock_data = {
            'symbol': sym,
            'clean_symbol': clean_sym,
            'sector': sector,
            'weight': weight_val,
            'beta': safe_float(data.iloc[k, beta_col]) if beta_col is not None else 0,
            'erb': safe_float(data.iloc[k, erb_col]) if erb_col is not None else 0,
            'action': str(data.iloc[k, action_col]) if action_col is not None else '',
            'status': status_val,
            # Carried through so consumers can tell a genuinely new position from
            # a top-up. The engine writes Status="Remained" even for a first-time
            # buy (SAILIFE, KRN and AVALON entered in Sep'26 with Prev_Qty 0 and
            # Action "BUY n", all marked Remained), so Status cannot be used for
            # this and prev_qty == 0 is the only reliable signal. Also brings
            # data.js in line with hq_data.js / ml_data.js, which already carry
            # qty and prev_qty.
            'qty': int(safe_float(data.iloc[k, qty_col])) if qty_col is not None else None,
            'prev_qty': int(safe_float(data.iloc[k, prev_col])) if prev_col is not None else None,
        }
        stocks.append(stock_data)
    return stocks

def trim_open_bar(df, date_col):
    """Drop today's row while the NSE session is still open, so the last row is
    always a COMPLETED daily close (avoids intraday price flicker in live market).
    After 15:30 IST today's bar is the final close and is kept."""
    if df.empty:
        return df
    now = datetime.now()  # server runs in IST
    mins = now.hour * 60 + now.minute
    market_open = now.weekday() < 5 and (9 * 60 + 15) <= mins <= (15 * 60 + 30)
    if market_open and df[date_col].iloc[-1].date() == now.date():
        return df.iloc[:-1]
    return df


def get_live_prices(symbols):
    """Last COMPLETED daily close per stock (today's open bar is ignored during
    market hours) plus the prior close and the MTD baseline."""
    results = {}
    for sym in symbols:
        found = False
        for folder in ['nifty50_host', 'nifty500_host', 'TOTAL_STOCKS']:
            path = os.path.join(folder, sym + '.csv') if not sym.endswith('.csv') else os.path.join(folder, sym)
            if not os.path.exists(path):
                path2 = os.path.join(folder, sym.replace('.csv','') + '.csv')
                if os.path.exists(path2):
                    path = path2
                else:
                    continue
            try:
                df = pd.read_csv(path)
                df.columns = [c.lower() for c in df.columns]
                # Parse dates robustly
                date_col = 'date' if 'date' in df.columns else df.columns[0]
                df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
                df = df.dropna(subset=[date_col]).sort_values(date_col).drop_duplicates(subset=[date_col], keep='last')
                # Drop any trailing bar with no recorded close (placeholder row
                # fetched before that day's official close posts) — same fix as
                # get_benchmark_live_and_mtd, so a blank close never reads as 0.
                df = df[pd.to_numeric(df['close'], errors='coerce').notna()]
                df = trim_open_bar(df, date_col)   # use last completed close, not intraday
                if len(df) < 2:
                    continue
                last = df.iloc[-1]
                prev = df.iloc[-2]
                last_close = safe_float(last.get('close', 0))
                prev_close = safe_float(prev.get('close', 0))
                chg = round((last_close / prev_close - 1) * 100, 2) if prev_close > 0 else 0

                # MTD baseline: last trading day of previous month
                now = datetime.now()
                prev_month_end = (now.replace(day=1) - pd.Timedelta(days=1))
                # Year-aware: a bare month comparison selects nothing every
                # January, which would silently make MTD read 0 all month.
                mtd_df = df[(df[date_col].dt.year < now.year) |
                            ((df[date_col].dt.year == now.year) &
                             (df[date_col].dt.month < now.month))]
                if not mtd_df.empty:
                    mtd_baseline = safe_float(mtd_df.iloc[-1].get('close', 0))
                else:
                    mtd_baseline = last_close  # fallback: no MTD if no prior month data
                mtd_chg = round((last_close / mtd_baseline - 1) * 100, 2) if mtd_baseline > 0 else 0

                results[sym] = {
                    'ltp': last_close,
                    'prev_close': prev_close,
                    'change_pct': chg,
                    'mtd_change_pct': mtd_chg,
                    'date': str(last.get(date_col, ''))
                }
                found = True
                break
            except:
                pass
        if not found:
            results[sym] = {'ltp': 0, 'prev_close': 0, 'change_pct': 0, 'mtd_change_pct': 0, 'date': 'N/A'}
    return results

def get_benchmark_live_and_mtd(bench_file, target_date=None):
    """Return (daily_change_pct, mtd_change_pct) for the benchmark index."""
    if not os.path.exists(bench_file):
        return 0.0, 0.0
    try:
        df = pd.read_csv(bench_file)
        # Try to find date column
        date_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), df.columns[0])
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
        df = df.dropna(subset=[date_col]).sort_values(date_col).drop_duplicates(subset=[date_col], keep='last')

        close_col = next((c for c in df.columns if 'close' in c.lower() or 'price' in c.lower()), None)
        if close_col is None:
            return 0.0, 0.0
        # Drop any trailing bar with no recorded close (e.g. a placeholder row
        # fetched before that day's official close posts) — a blank close is
        # never a real completed session, regardless of trim_open_bar's
        # market-hours heuristic below.
        df = df[pd.to_numeric(df[close_col], errors='coerce').notna()]
        df = trim_open_bar(df, date_col)   # last completed close, not intraday

        # Align with target_date if provided (useful when stock data is lagging)
        if target_date:
            try:
                t_dt = pd.to_datetime(target_date)
                df = df[df[date_col] <= t_dt]
            except:
                pass

        if len(df) < 2:
            return 0.0, 0.0
        last_close = safe_float(df.iloc[-1][close_col])
        prev_close = safe_float(df.iloc[-2][close_col])
        daily = round((last_close / prev_close - 1) * 100, 2) if prev_close > 0 else 0.0

        # MTD baseline = last close of the previous CALENDAR month, matching
        # get_live_prices(). Anchoring on the last ROW's month instead meant
        # that on the 1st of a new month -- before any session had traded -- the
        # benchmark reported the whole of last month while the portfolio
        # correctly reported 0.00%, so the dashboard showed a fabricated MTD
        # alpha (+1.24% on Nifty 50, 01-09-2026) for a book yet to trade.
        now = datetime.now()
        mtd_df = df[(df[date_col].dt.year < now.year) |
                    ((df[date_col].dt.year == now.year) &
                     (df[date_col].dt.month < now.month))]
        if not mtd_df.empty:
            mtd_baseline = safe_float(mtd_df.iloc[-1][close_col])
        else:
            mtd_baseline = last_close
        mtd = round((last_close / mtd_baseline - 1) * 100, 2) if mtd_baseline > 0 else 0.0
        return daily, mtd
    except:
        return 0.0, 0.0

def get_sector_map():
    mapping = {}
    for f in ['ind_nifty50list.csv', 'ind_nifty500list.csv']:
        if not os.path.exists(f):
            continue
        df = pd.read_csv(f)
        sym_col = next((c for c in df.columns if 'Symbol' in c), None)
        ind_col = next((c for c in df.columns if 'Industry' in c or 'Sector' in c), None)
        if sym_col and ind_col:
            for _, row in df.iterrows():
                mapping[str(row[sym_col]).strip()] = str(row[ind_col]).strip()

    # Augment with the TOTAL_STOCKS (759) universe — each CSV carries Symbol/Industry.
    tdir = 'TOTAL_STOCKS'
    if os.path.isdir(tdir):
        for fn in os.listdir(tdir):
            if not fn.endswith('.csv'):
                continue
            try:
                d = pd.read_csv(os.path.join(tdir, fn), nrows=1, usecols=['Symbol', 'Industry'])
                sym = str(d['Symbol'].iloc[0]).strip()
                ind = str(d['Industry'].iloc[0]).strip()
                if sym and sym not in mapping and ind and ind.lower() != 'nan':
                    mapping[sym] = ind
            except Exception:
                pass
    return mapping

def get_exec_history(xl):
    try:
        df = pd.read_excel(xl, sheet_name='Execution_History')
        df = df.fillna('')
        records = []
        for _, row in df.iterrows():
            records.append({
                'month': str(row.get('Month','')),
                'symbol': str(row.get('Symbol','')),
                'action': str(row.get('Action','')),
                'qty': int(row.get('Qty', 0)) if row.get('Qty','') != '' else 0,
                'price': safe_float(row.get('Price', 0)),
                'return': safe_float(row.get('Return', 0))
            })
        return records[-30:]  # last 30 trades
    except:
        return []

def get_stock_correlation(symbols):
    """Calculate daily return correlation matrix for the given symbols."""
    # Filter out header garbage like 'Stock'
    symbols = [s for s in symbols if s and s not in ('Stock', 'nan', 'None')]
    if not symbols:
        return {"symbols": [], "matrix": []}
    
    returns_map = {}
    for sym in symbols:
        found = False
        for folder in ['nifty50_host', 'nifty500_host', 'TOTAL_STOCKS']:
            path = os.path.join(folder, sym + '.csv') if not sym.endswith('.csv') else os.path.join(folder, sym)
            if not os.path.exists(path):
                path2 = os.path.join(folder, sym.replace('.csv','') + '.csv')
                if os.path.exists(path2): path = path2
                else: continue
            try:
                # Get last 120 days for a robust correlation
                df = pd.read_csv(path).tail(120)
                df.columns = [c.lower() for c in df.columns]
                
                # IMPORTANT: Use date as index to align different stocks
                date_col = 'date' if 'date' in df.columns else 'time'
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
                    df.set_index(date_col, inplace=True)
                    df = df[~df.index.duplicated(keep='last')]
                
                if len(df) > 10:
                    df['ret'] = df['close'].pct_change()
                    returns_map[sym.split('_')[0]] = df['ret'].dropna()
                    found = True
                    break
            except: pass
    
    if not returns_map:
        return {"symbols": [], "matrix": []}
        
    # Align by date index
    df_ret = pd.DataFrame(returns_map).dropna(how='all')
    if df_ret.empty:
        return {"symbols": [], "matrix": []}
        
    # Fill missing values with 0 to allow correlation calculation if some days are missing
    df_ret = df_ret.fillna(0)
    
    corr = df_ret.corr().round(3)
    # Convert to list of lists for JSON
    return {
        "symbols": list(corr.columns),
        "matrix": corr.values.tolist()
    }

# ============================================================
# MAIN EXTRACTION
# ============================================================

sector_map = get_sector_map()
print(f"[*] Sector map loaded: {len(sector_map)} stocks")

output = {}

# Universe -> (summary workbook, deep-dive workbook, benchmark file).
# total759 = the broad TOTAL_STOCKS universe, benchmarked against Nifty 500.
UNIVERSES = {
    'nifty50':  {'summary': 'Hedge_nifty50.xlsx',         'deep': 'Hedge_Institutional_Deep_Dive_nifty50.xlsx',  'bench': 'NIFTY50_1d.csv'},
    'nifty500': {'summary': 'Hedge_nifty500.xlsx',        'deep': 'Hedge_Institutional_Deep_Dive_nifty500.xlsx', 'bench': 'NIFTY500_1d.csv'},
    'total759': {'summary': 'Hedge_Pro_Summary_759.xlsx', 'deep': 'Hedge_Institutional_Deep_Dive_759.xlsx',      'bench': 'NIFTY500_1d.csv'},
}

for universe, cfg in UNIVERSES.items():
    fname = cfg['summary']
    dd_fname = cfg['deep']

    if not os.path.exists(fname):
        print(f"\n[WARN] {fname} not found — skipping universe '{universe}'.")
        continue

    print(f"\n[*] Processing {fname}...")
    xl = pd.ExcelFile(fname)
    
    # 1. Executive Summary (all 7 layers + Benchmark)
    df_exec = pd.read_excel(xl, sheet_name='Executive_Dashboard')
    exec_data = {}
    for _, row in df_exec.iterrows():
        metric = str(row['Metric']).strip()
        exec_data[metric] = {
            'Base': safe_float(row.get('Base SIM', 0)),
            'ST': safe_float(row.get('ST Filter', 0)),
            'EMA': safe_float(row.get('EMA Filter', 0)),
            'COMBO': safe_float(row.get('COMBO Filter', 0)),
            'ULTRA': safe_float(row.get('ULTRA Layer', 0)),
            'COMBO_HEDGE': safe_float(row.get('COMBO+Hedge', 0)),
            'ULTRA_HEDGE': safe_float(row.get('ULTRA Defense', 0)),
            'Bench': safe_float(row.get('Benchmark', 0)),
        }
    
    # 2. Monthly Summary (all returns for all layers)
    df_sum = pd.read_excel(xl, sheet_name='Detailed_Monthly_Summary')
    df_sum['Month'] = df_sum['Month'].astype(str)
    
    # Avg Ex-Ante Sharpe from the actual monthly column
    avg_ex_ante_sr = round(float(df_sum['Ex_Ante_Sharpe'].mean()), 2)
    
    # 3. Computed metrics for all 7 layers + Benchmark
    bench_returns = df_sum['Bench'].values
    layer_metrics = {}
    for layer in ['Base', 'ST', 'EMA', 'COMBO', 'ULTRA', 'COMBO_HEDGE', 'ULTRA_HEDGE', 'Bench']:
        metrics = compute_metrics(df_sum[layer].values, bench_returns)
        if layer == 'Bench':
            metrics['Alpha'] = 0.0
        layer_metrics[layer] = metrics
    
    # 4. Equity Curves (cumulative)
    equity_curves = get_equity_curves(df_sum)
    
    # 5. Churning Analysis
    try:
        df_churn = pd.read_excel(xl, sheet_name='Churning_Analysis')
        df_churn['Month'] = df_churn['Month'].astype(str)
        churning_data = df_churn.to_dict(orient='records')
        for row in churning_data:
            for k, v in row.items():
                if isinstance(v, float):
                    row[k] = safe_float(v)
    except:
        churning_data = []
    
    # 5. Heatmaps for all 7 layers
    heatmaps = {}
    for layer in ['Base', 'ST', 'EMA', 'COMBO', 'ULTRA', 'COMBO_HEDGE', 'ULTRA_HEDGE', 'Bench']:
        heatmaps[layer] = get_heatmap_data(df_sum, layer)
    
    # 6. Monthly detail rows (only include columns that exist)
    wanted_cols = ['Month', 'Trade_Month', 'Port_Beta', 'Ex_Ante_Sharpe', 'Ex_Ante_Sortino',
                   'Stock_Count', 'Added', 'Removed',
                   'Base', 'ST', 'EMA', 'COMBO', 'ULTRA',
                   'COMBO_HEDGE', 'ULTRA_HEDGE', 'Bench']
    available_cols = [c for c in wanted_cols if c in df_sum.columns]
    monthly_detail = df_sum[available_cols].to_dict(orient='records')

    
    # Clean floats
    for row in monthly_detail:
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = safe_float(v)
    
    # 7. Current Portfolio with Sector Map
    current_portfolio = get_current_portfolio(xl, sector_map)
    
    # 8. Live Prices for portfolio stocks
    symbols = [s['symbol'] for s in current_portfolio]
    live_prices = get_live_prices(symbols)
    
    # Inject live prices into portfolio
    for s in current_portfolio:
        live = live_prices.get(s['symbol'], {})
        s['ltp'] = live.get('ltp', 0)
        s['change_pct'] = live.get('change_pct', 0)
        s['mtd_change_pct'] = live.get('mtd_change_pct', 0)
        s['prev_close'] = live.get('prev_close', 0)
        s['date'] = live.get('date', '')
    
    # 9. Execution History from Deep Dive
    exec_history = []
    if os.path.exists(dd_fname):
        xl_dd = pd.ExcelFile(dd_fname)
        exec_history = get_exec_history(xl_dd)
        # Inject sector into exec history
        for t in exec_history:
            clean = t['symbol'].split('_')[0]
            t['sector'] = sector_map.get(clean, 'Other')
    
    # 10. Stock Correlation Matrix for Current Portfolio
    stock_corr = get_stock_correlation(symbols)

    # 11. Live & MTD performance for portfolio and benchmark
    bench_file = cfg['bench']
    
    # Extract last available date from stocks to align benchmark
    stock_last_date = None
    for lp in live_prices.values():
        if lp.get('date') and lp['date'] != 'N/A':
            stock_last_date = lp['date']
            break
            
    bench_daily, bench_mtd = get_benchmark_live_and_mtd(bench_file, target_date=stock_last_date)

    # Weighted daily and MTD return across portfolio stocks
    total_wt = sum(s['weight'] for s in current_portfolio if s['weight'] > 0)
    port_daily = 0.0
    port_mtd   = 0.0
    if total_wt > 0:
        port_daily = round(sum(s['change_pct'] * s['weight'] for s in current_portfolio) / total_wt, 2)
        port_mtd   = round(sum(s['mtd_change_pct'] * s['weight'] for s in current_portfolio) / total_wt, 2)

    output[universe] = {
        'exec_summary': exec_data,
        'avg_ex_ante_sr': avg_ex_ante_sr,
        'layer_metrics': layer_metrics,
        'equity_curves': equity_curves,
        'churning_data': churning_data,
        'heatmaps': heatmaps,
        'monthly_detail': monthly_detail,
        'current_portfolio': current_portfolio,
        'exec_history': exec_history,
        'stock_correlation': stock_corr,
        'total_months': len(df_sum),
        'live_performance': {
            'portfolio_ret':   port_daily,
            'benchmark_ret':   bench_daily,
            'alpha':           round(port_daily - bench_daily, 2),
            'portfolio_mtd':   port_mtd,
            'benchmark_mtd':   bench_mtd,
            'alpha_mtd':       round(port_mtd - bench_mtd, 2),
            'indicator':       'up' if port_daily >= 0 else 'down'
        }
    }
    print(f"  [OK] {universe}: {len(df_sum)} months | port_daily={port_daily:+.2f}% | port_mtd={port_mtd:+.2f}%")

output['sector_map'] = sector_map
output['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")

# Write JS data file
with open('data.js', 'w') as f:
    f.write("const DASHBOARD_DATA = ")
    json.dump(output, f, indent=2)
    f.write(";")

print("\n[OK] data.js exported successfully.")

# ── Auto-bump cache-buster in index.html ──────────────────────────────────────
import re as _re
import time as _time

_ver = int(_time.time())          # unique integer every run, e.g. 1747127665
_html_path = 'index.html'

if os.path.exists(_html_path):
    with open(_html_path, 'r', encoding='utf-8') as _fh:
        _html = _fh.read()

    # Replace  ?v=<anything>  on the data.js and app.js lines
    _html = _re.sub(r'(src="data\.js)\?v=\d+(")', rf'\g<1>?v={_ver}\g<2>', _html)
    _html = _re.sub(r'(src="app\.js)\?v=\d+(")',  rf'\g<1>?v={_ver}\g<2>', _html)

    with open(_html_path, 'w', encoding='utf-8') as _fh:
        _fh.write(_html)

    print(f"[OK] index.html cache-buster updated -> v={_ver}")
else:
    print("[WARN] index.html not found — cache-buster NOT updated.")
