"""
update_indices.py
-----------------
Bring the benchmark index CSVs up to the latest completed session.

Replaces the deleted data_set_nifty5.py / data_set_nifty500.py / index_data.py.

Two rules this enforces that the old pipeline did not:

  * A bar with no Close is never written. On 28-08-2026 both files ended with
    "...,24076.849609375,,,0" -- Open/High/Low but a blank Close and zero volume.
    Everything downstream reads Close, so that row produced "+nan%" daily and MTD
    returns on the dashboards. Yahoo itself has no 28-08 bar for ^NSEI/^CRSLDX,
    so the row was never real.
  * Existing rows whose Close is blank are dropped on the way through, which is
    what repairs a file the old pipeline already damaged.

    python update_indices.py             # append through the last closed session
    python update_indices.py --dry-run   # report, write nothing
"""
import csv
import os
import sys
from datetime import datetime, timedelta

import yfinance as yf

MAIN = os.path.dirname(os.path.abspath(__file__))
DATE_FMT = "%d-%m-%Y"
MARKET_CLOSE = (15, 30)

INDICES = [
    ("NIFTY50", "^NSEI", "NIFTY50_1d.csv"),
    ("NIFTY500", "^CRSLDX", "NIFTY500_1d.csv"),
]
HEADER = ["Index Name", "Symbol", "Date", "Open", "High", "Low",
          "Close", "Adj Close", "Volume"]

# The TradingView-shape benchmarks som_hedge.py reads, which live beside the
# engine in the shared folder rather than here. Same index, different export
# shape: time,open,high,low,close,Volume with an ISO date. NSE_CNX500 is the
# benchmark for the Nifty 500 and 759 books -- it was a month stale (30-07-2026)
# while the books it benchmarks were being asked for an August signal month.
SHARED = os.environ.get("PORTFOLIO_SHARED", r"D:\Shared folder\portfolio")
TV_INDICES = [
    ("^CRSLDX", "NSE_CNX500, 1D.csv"),
]

DRY_RUN = "--dry-run" in sys.argv
INCLUDE_TODAY = "--include-today" in sys.argv


def session_closed():
    now = datetime.now()
    return (now.hour, now.minute) >= MARKET_CLOSE


def load(path):
    """Existing rows, minus any with a blank/unparseable Close."""
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    keep, dropped = [], []
    for r in body:
        if len(r) < 7:
            continue
        close = r[6].strip()
        if not close:
            dropped.append(r[2])
            continue
        try:
            float(close)
        except ValueError:
            dropped.append(r[2])
            continue
        keep.append(r)
    return header, keep, dropped


def main():
    drop_today = not (INCLUDE_TODAY or session_closed())
    today_str = datetime.today().strftime(DATE_FMT)
    if drop_today:
        print(f"session still open - dropping partial bar for {today_str}")

    for name, ticker, fname in INDICES:
        path = os.path.join(MAIN, fname)
        if not os.path.exists(path):
            print(f"[skip] {fname} not found")
            continue
        header, rows, dropped = load(path)
        dates = {r[2].strip() for r in rows}
        last = max(datetime.strptime(d, DATE_FMT) for d in dates)
        print(f"\n{name} ({ticker}): {len(rows)} good rows, last {last:%d-%m-%Y}")
        if dropped:
            print(f"   dropping {len(dropped)} row(s) with no Close: {dropped}")

        start = (last + timedelta(days=1)).strftime("%Y-%m-%d")
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.Ticker(ticker).history(start=start, end=end, interval="1d",
                                       auto_adjust=False)
        new = []
        if df is not None and not df.empty:
            for idx, r in df.iterrows():
                ds = idx.strftime(DATE_FMT)
                if ds in dates or (drop_today and ds == today_str):
                    continue
                close = r.get("Close")
                if close is None or close != close:      # NaN guard
                    print(f"   skipping {ds}: no Close from the source")
                    continue
                adj = r.get("Adj Close", close)
                if adj is None or adj != adj:
                    adj = close
                new.append([name, ticker, ds, r.get("Open", ""), r.get("High", ""),
                            r.get("Low", ""), close, adj,
                            int(r.get("Volume", 0) or 0)])
                dates.add(ds)

        if new:
            print(f"   +{len(new)} session(s) -> last {new[-1][2]}")
        else:
            print("   no new sessions")

        if DRY_RUN:
            print("   DRY RUN - not written")
            continue
        if not new and not dropped:
            continue

        out = rows + new
        out.sort(key=lambda r: datetime.strptime(r[2].strip(), DATE_FMT))
        assert len({r[2] for r in out}) == len(out), "duplicate date in output"
        assert all(str(r[6]).strip() for r in out), "row with blank Close survived"
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header if len(header) == len(HEADER) else HEADER)
            w.writerows(out)
        print(f"   wrote {path} ({len(out)} rows)")


def update_tv(ticker, fname, drop_today, today_str):
    """Extend a TradingView-shape index export (time,open,high,low,close,Volume)."""
    path = os.path.join(SHARED, fname)
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if len(r) >= 5 and r[4].strip()]
    dates = {r[0].strip() for r in body}
    last = max(datetime.strptime(d, "%Y-%m-%d") for d in dates)
    print(f"\n{fname} ({ticker}): {len(body)} rows, last {last:%Y-%m-%d}")

    df = yf.Ticker(ticker).history(
        start=(last + timedelta(days=1)).strftime("%Y-%m-%d"),
        end=(datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d", auto_adjust=False)
    new = []
    if df is not None and not df.empty:
        for idx, r in df.iterrows():
            ds = idx.strftime("%Y-%m-%d")
            close = r.get("Close")
            if ds in dates or close is None or close != close:
                continue
            if drop_today and idx.strftime(DATE_FMT) == today_str:
                continue
            new.append([ds, r.get("Open", ""), r.get("High", ""), r.get("Low", ""),
                        close, int(r.get("Volume", 0) or 0)])
            dates.add(ds)
    if not new:
        print("   no new sessions")
        return
    print(f"   +{len(new)} session(s) -> last {new[-1][0]}")
    if DRY_RUN:
        print("   DRY RUN - not written")
        return
    out = body + new
    out.sort(key=lambda r: r[0])
    assert len({r[0] for r in out}) == len(out), "duplicate date in output"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(out)
    print(f"   wrote {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
    _drop = not (INCLUDE_TODAY or session_closed())
    _today = datetime.today().strftime(DATE_FMT)
    for _tk, _fn in TV_INDICES:
        update_tv(_tk, _fn, _drop, _today)
