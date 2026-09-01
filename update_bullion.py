"""
Refresh the bullion price CSVs (GOLDBEES / SILVERBEES) from yfinance.

Incremental: a short trailing overlap is re-fetched and everything older is
left alone, so the history is never rebuilt from scratch. Both copies are kept
in sync — the one in this folder (read by the report extractors) and the one in
the shared portfolio folder (read by som_metals.py during the backtest).

Safe to run at any hour, including while the market is open: the session that
is still forming is never written. That matters because this runs unattended
from Task Scheduler — an intraday snapshot written as a settled daily close
would otherwise be frozen into history permanently.

The on-disk format is the TradingView export shape the engine already expects:
    time,open,high,low,close,Volume      with time as YYYY-MM-DD

Usage:
  python update_bullion.py
"""
import datetime as dt
import os
import sys

import pandas as pd
import yfinance as yf

MAIN = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("PORTFOLIO_SHARED", r"D:\Shared folder\portfolio")

FILES = [
    ("GOLDBEES.NS", "NSE_GOLDBEES, 1D.csv"),
    ("SILVERBEES.NS", "NSE_SILVERBEES, 1D.csv"),
]
COLS = ["time", "open", "high", "low", "close", "Volume"]
PRICE_COLS = ["open", "high", "low", "close"]

# How far back to re-ask. Only needs to cover a long weekend plus a holiday —
# its job is to let a corrected close replace a bar written by an earlier run,
# not to rebuild history.
OVERLAP_DAYS = 7

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SESSION_CLOSE = dt.time(15, 30)     # NSE cash market


def last_complete_session():
    """The most recent date whose bar can be trusted as final."""
    now = dt.datetime.now(IST)
    if now.time() < SESSION_CLOSE:
        return now.date() - dt.timedelta(days=1)
    return now.date()


def refresh(ticker, name):
    path = os.path.join(MAIN, name)
    if not os.path.exists(path):
        sys.exit(f"[error] {path} not found — this script only extends existing history")

    old = pd.read_csv(path, parse_dates=["time"]).sort_values("time")
    last = old["time"].max()
    cutoff = last_complete_session()
    print(f"\n{ticker}: {len(old)} rows, last {last.date()}")

    # Start behind the last stored date rather than after it. Re-asking for the
    # overlap is what lets a settled close replace a bar an earlier run wrote
    # while it was still moving.
    start = (last - pd.Timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, progress=False, auto_adjust=False)
    if df.empty:
        print("   nothing returned — already up to date")
        return old, path

    if isinstance(df.columns, pd.MultiIndex):     # yfinance returns MultiIndex per-ticker
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index().rename(columns={
        "Date": "time", "Open": "open", "High": "high", "Low": "low", "Close": "close"})
    df = df[COLS].dropna(subset=["close"])

    # Drop the session that has not settled yet.
    df = df[df["time"].dt.date <= cutoff]
    if df.empty:
        print("   nothing returned — already up to date")
        return old, path

    # The fetched rows must land after their stored counterparts so that
    # keep="last" prefers them; a stable sort is what guarantees that ordering
    # survives, since the two share a `time`.
    out = pd.concat([old[COLS], df], ignore_index=True)
    out = out.sort_values("time", kind="stable").drop_duplicates(subset=["time"], keep="last")

    added = int((out["time"] > last).sum())
    revised = compare_overlap(old, out)
    if added:
        print(f"   +{added} new sessions -> last {out['time'].max().date()}")
    else:
        print(f"   no new sessions (last {out['time'].max().date()})")
    if revised:
        print(f"   corrected {revised} previously written bar(s)")
    return out, path


def compare_overlap(old, out):
    """How many already-stored bars changed value — i.e. were partial before."""
    a = old.set_index("time")[PRICE_COLS].round(2)
    b = out.set_index("time")[PRICE_COLS].round(2)
    shared = a.index.intersection(b.index)
    return int((a.loc[shared] != b.loc[shared]).any(axis=1).sum())


def main():
    for ticker, name in FILES:
        out, path = refresh(ticker, name)
        out = out.copy()
        out["time"] = pd.to_datetime(out["time"]).dt.strftime("%Y-%m-%d")
        # Match the 2-decimal shape of the original export; raw float64 writes
        # 125.83000183105469 for what the exchange quoted as 125.83.
        out[PRICE_COLS] = out[PRICE_COLS].round(2)
        out["Volume"] = out["Volume"].fillna(0).astype("int64")
        for target in (path, os.path.join(SHARED, name)):
            if os.path.isdir(os.path.dirname(target)):
                out.to_csv(target, index=False)
                print(f"   wrote {target}")
            else:
                print(f"   [warn] {os.path.dirname(target)} not found — skipped")


if __name__ == "__main__":
    main()
