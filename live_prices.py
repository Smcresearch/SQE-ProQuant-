"""
live_prices.py
--------------
Last completed close, prior close and month-to-date baseline for a list of
symbols, read from the local per-stock CSVs.

Factored out because build_hq_backtest_dashboard.py and extract_ml.py each grew
their own copy and each got it wrong in the same two ways. Both fetched from
yfinance and both measured MTD against the month of the LAST BAR:

  * yfinance returns a placeholder bar for a session that has not happened yet.
    Rebuilt just after midnight on 01-09-2026, 18 of 22 High Quality holdings
    came back with a "01-09" bar whose close equalled the 31-08 close, so every
    daily change rendered as 0.00%.
  * Measuring MTD from the last bar's month means that when the last bar is not
    in the current month, "month to date" silently becomes the PREVIOUS month's
    full return -- ATHERENERG showed +36.29% MTD on the first day of a September
    book that had not traded yet.

Reading the same settled CSVs the backtest used avoids both: they contain only
completed sessions, and the MTD baseline is taken from the calendar month we are
actually in.

    from live_prices import price_symbols
    quotes = price_symbols(['EMMVEE', 'GSPCROP'], ['hq_quarterly_universe'])
"""
import os
from datetime import datetime

import pandas as pd

MAIN = os.path.dirname(os.path.abspath(__file__))
MARKET_OPEN_MIN = 9 * 60 + 15
MARKET_CLOSE_MIN = 15 * 60 + 30


def _candidates(folder, sym):
    """The two naming conventions in use across the price folders."""
    return [os.path.join(folder, sym + ".csv"),
            os.path.join(folder, sym + "_1d_max.csv")]


def _trim_open_bar(df, date_col):
    """Drop today's row while the session is still open, so the last row is
    always a completed close. After 15:30 IST today's bar is final and kept."""
    if df.empty:
        return df
    now = datetime.now()
    mins = now.hour * 60 + now.minute
    if (now.weekday() < 5 and MARKET_OPEN_MIN <= mins <= MARKET_CLOSE_MIN
            and df[date_col].iloc[-1].date() == now.date()):
        return df.iloc[:-1]
    return df


def _load(path):
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    date_col = "date" if "date" in df.columns else df.columns[0]
    # Two date shapes are in play and guessing wrong silently reorders history:
    # the per-stock CSVs are DD-MM-YYYY, the TradingView bullion exports are
    # ISO. Passing dayfirst=True at an ISO date turned 2026-08-12 into 12 Dec,
    # which made SILVERBEES the "latest" bar and produced a 7.43% MTD on a book
    # that had not traded. Pick the format from the data instead of assuming.
    sample = df[date_col].astype(str).str.strip()
    sample = sample[sample.ne("") & sample.ne("nan")]
    iso = bool(len(sample)) and sample.iloc[0][:4].isdigit() and "-" in sample.iloc[0][4:6]
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=not iso,
                                  format="%Y-%m-%d" if iso else None,
                                  errors="coerce")
    df = (df.dropna(subset=[date_col])
            .sort_values(date_col)
            .drop_duplicates(subset=[date_col], keep="last"))
    # A trailing row with no close is a placeholder written before the official
    # close posted -- it must not read as a price of 0.
    df = df[pd.to_numeric(df["close"], errors="coerce").notna()]
    return df, date_col


def price_symbols(symbols, folders, asof=None, aliases=None):
    """{symbol: {ltp, prev_close, change_pct, mtd_change_pct, date}}.

    aliases maps a symbol to an explicit CSV path, for holdings whose file does
    not follow either naming convention -- the bullion sleeve is stored as
    "NSE_GOLDBEES, 1D.csv" in the TradingView export shape (time,open,...).

    Symbols with no CSV anywhere are returned with ltp 0 so the caller can decide
    what to do -- this module never invents a price.
    """
    now = asof or datetime.now()
    aliases = aliases or {}
    out = {}
    for sym in symbols:
        rec = {"ltp": 0.0, "prev_close": 0.0, "change_pct": 0.0,
               "mtd_change_pct": 0.0, "date": "N/A"}
        search = []
        if sym in aliases:
            a = aliases[sym]
            search.append(a if os.path.isabs(a) else os.path.join(MAIN, a))
        for folder in folders:
            folder = folder if os.path.isabs(folder) else os.path.join(MAIN, folder)
            search.extend(_candidates(folder, sym))
        for path in search:
            if not os.path.exists(path):
                continue
            try:
                df, date_col = _load(path)
                df = _trim_open_bar(df, date_col)
            except Exception:
                continue
            if len(df) < 2:
                continue
            close = pd.to_numeric(df["close"], errors="coerce")
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2])

            # MTD baseline = last close of the PREVIOUS calendar month, i.e.
            # where this month's book started. Anchored on the calendar, not on
            # the last bar's month.
            before = df[(df[date_col].dt.year < now.year) |
                        ((df[date_col].dt.year == now.year) &
                         (df[date_col].dt.month < now.month))]
            base = float(pd.to_numeric(before["close"], errors="coerce").iloc[-1]) \
                if not before.empty else last

            rec = {
                "ltp": round(last, 2),
                "prev_close": round(prev, 2),
                "change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
                "mtd_change_pct": round((last / base - 1) * 100, 2) if base else 0.0,
                "date": df[date_col].iloc[-1].strftime("%Y-%m-%d"),
            }
            break
        out[sym] = rec
    return out


def aggregate(holdings):
    """Weighted portfolio daily / MTD return over holdings carrying weight,
    change_pct and mtd_change_pct. Mirrors extract_dashboard_data.py."""
    tw = sum(h["weight"] for h in holdings if h.get("weight", 0) > 0)
    if not tw:
        return 0.0, 0.0
    daily = sum(h["change_pct"] * h["weight"] for h in holdings) / tw
    mtd = sum(h["mtd_change_pct"] * h["weight"] for h in holdings) / tw
    return round(daily, 2), round(mtd, 2)
