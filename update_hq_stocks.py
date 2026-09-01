"""
update_hq_stocks.py
-------------------
Bring every CSV in the High Quality universe folder up to the latest completed
session. Companion to update_stocks.py, which targets TOTAL_STOCKS and uses a
different column order (Date at index 5 there, index 4 here).

HQ schema: Symbol,Company,Industry,Index,Date,Open,High,Low,Close,Volume,Dividends,Stock Splits

Static columns (Symbol/Company/Industry/Index) are carried from the file's first
data row, so the appended rows stay schema-identical. Dates already present are
skipped, so the script is safe to re-run.

While the NSE session is still open, today's bar is partial and is dropped
unless --include-today is passed.

    python update_hq_stocks.py                 # all CSVs in HQ_DIR
    python update_hq_stocks.py --dry-run       # report gaps, write nothing
    python update_hq_stocks.py --include-today # keep an in-progress bar
"""
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

HQ_DIR = os.environ.get('HQ_STOCKS_DIR', r'D:/Shared folder/portfolio/High_Quality_stocks')
DATE_FMT = '%d-%m-%Y'
NSE_SUFFIX = '.NS'
BSE_SUFFIX = '.BO'
SLEEP_BETWEEN = 0.2
MARKET_CLOSE_HOUR = 15      # NSE closes 15:30 IST
MARKET_CLOSE_MIN = 30

# CSV name -> Yahoo ticker that actually carries the history. Same idea as the
# RENAMES table in fetch_nifty500_hist.py: the basket keeps its original symbol
# so the screener still matches, but the download follows the corporate action.
RENAMES = {
    'ADORWELD':  'ADOR.NS',        # NSE symbol is ADOR (master token 34)
    'KLBRENG':   'KLBRENG-B.NS',   # re-series'd to KLBRENG-B
    'SELAN':     'ANTELOPUS.NS',   # Selan Exploration -> Antelopus Energy
    'MODERNINS': '515008.BO',      # Modern Insulators is BSE-only (grp XT)
}

DRY_RUN = '--dry-run' in sys.argv
INCLUDE_TODAY = '--include-today' in sys.argv


def read_csv_meta(path):
    """(static_cols, set_of_dates, last_date) from an existing HQ CSV."""
    static, dates, last = None, set(), None
    with open(path, 'r', encoding='utf-8') as f:
        next(f, None)                       # header
        for line in f:
            parts = line.rstrip('\n').split(',')
            if len(parts) < 5:
                continue
            if static is None:
                static = parts[:4]          # Symbol, Company, Industry, Index
            d = parts[4].strip()
            if not d:
                continue
            dates.add(d)
            try:
                dt = datetime.strptime(d, DATE_FMT)
            except ValueError:
                continue
            if last is None or dt > last:
                last = dt
    return static, dates, last


def fetch(symbol, start_dt):
    """Daily bars from the day after start_dt. NSE first, BSE as fallback."""
    start = (start_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    end = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    if symbol in RENAMES:
        candidates = [RENAMES[symbol]]
    else:
        candidates = [symbol + NSE_SUFFIX, symbol + BSE_SUFFIX]
    for tk in candidates:
        try:
            df = yf.Ticker(tk).history(
                start=start, end=end, interval='1d',
                auto_adjust=True, actions=True)
            if df is not None and not df.empty:
                return df, tk
        except Exception as e:
            print(f'    yfinance error {tk}: {e}')
    return None, None


def session_closed_today():
    now = datetime.now()
    return (now.hour, now.minute) >= (MARKET_CLOSE_HOUR, MARKET_CLOSE_MIN)


def main():
    files = sorted(f for f in os.listdir(HQ_DIR) if f.lower().endswith('.csv'))
    print(f'[hq] {len(files)} CSVs in {HQ_DIR}')
    drop_today = not (INCLUDE_TODAY or session_closed_today())
    today_str = datetime.today().strftime(DATE_FMT)
    if drop_today:
        print(f'[hq] session still open - dropping partial bar for {today_str}')
    if DRY_RUN:
        print('[hq] DRY RUN - no files will be written')

    updated = skipped = failed = total_rows = 0
    stale = []
    for i, fn in enumerate(files, 1):
        sym = fn[:-4]
        path = os.path.join(HQ_DIR, fn)
        static, dates, last = read_csv_meta(path)
        if static is None or last is None:
            print(f'  [{i:3}/{len(files)}] {sym:<12} UNREADABLE - skipped')
            failed += 1
            continue

        df, used = fetch(sym, last)
        if df is None:
            print(f'  [{i:3}/{len(files)}] {sym:<12} no data since {last:%d-%m-%Y}')
            failed += 1
            stale.append((sym, last))
            time.sleep(SLEEP_BETWEEN)
            continue

        rows = []
        for idx, r in df.iterrows():
            ds = idx.strftime(DATE_FMT)
            if ds in dates:
                continue
            if drop_today and ds == today_str:
                continue
            rows.append(','.join(static + [
                ds, str(r.get('Open', 0.0)), str(r.get('High', 0.0)),
                str(r.get('Low', 0.0)), str(r.get('Close', 0.0)),
                str(int(r.get('Volume', 0) or 0)),
                str(r.get('Dividends', 0.0)), str(r.get('Stock Splits', 0.0))]))

        if rows:
            if not DRY_RUN:
                with open(path, 'a', encoding='utf-8', newline='') as f:
                    f.write('\n'.join(rows) + '\n')
            print(f'  [{i:3}/{len(files)}] {sym:<12} +{len(rows):>3} rows '
                  f'({last:%d-%m-%Y} -> {rows[-1].split(",")[4]})  [{used}]')
            updated += 1
            total_rows += len(rows)
        else:
            skipped += 1
        time.sleep(SLEEP_BETWEEN)

    print(f'\n[hq] updated {updated} | already current {skipped} | failed {failed} '
          f'| {total_rows} rows appended')
    if stale:
        print('[hq] no fresh data for:')
        for s, d in stale:
            print(f'      {s:<12} last {d:%d-%m-%Y}')


if __name__ == '__main__':
    main()
