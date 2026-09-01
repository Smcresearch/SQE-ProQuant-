"""
update_stocks.py
----------------
Bring every per-stock CSV up to the latest completed session, across all four
price folders the pipeline reads.

The folders do NOT share a column order:
    TOTAL_STOCKS, hq_quarterly_universe   Company,Industry,Symbol,Series,ISIN,Date,...
    nifty50_host, nifty500_host           Symbol,Company,Industry,Index,Date,...
and hq_quarterly_universe actually mixes both shapes file by file.

The previous version hardcoded Date at column 5. In the nifty*_host folders that
column holds Open, so its "already present?" guard compared prices against dates,
never matched, and re-appended the same session on every run -- 2,762 duplicate
rows had accumulated by 31-08-2026, and a repeated date breaks any reindex on the
daily series downstream. Selecting Date BY COLUMN NAME per file is the fix, and
it is why one script can now cover all four folders.

Dates already present are skipped, so this is safe to re-run. While the NSE
session is still open today's bar is partial and is dropped unless
--include-today is passed.

    python update_stocks.py                    # all folders
    python update_stocks.py TOTAL_STOCKS       # only these
    python update_stocks.py --dry-run          # report gaps, write nothing
"""
import csv
import os
import sys
import time
from datetime import datetime, timedelta

import yfinance as yf

MAIN = os.path.dirname(os.path.abspath(__file__))
FOLDERS = ["TOTAL_STOCKS", "nifty50_host", "nifty500_host", "hq_quarterly_universe"]
DATE_FMT = "%d-%m-%Y"
SLEEP_BETWEEN = 0.15
MARKET_CLOSE = (15, 30)          # NSE cash market, IST

# CSV name -> the Yahoo ticker that actually carries the history. Same table
# update_hq_stocks.py keeps: the basket holds its original symbol so the
# screener still matches, but the download follows the corporate action.
RENAMES = {
    "ADORWELD": "ADOR.NS",
    "KLBRENG": "KLBRENG-B.NS",
    "SELAN": "ANTELOPUS.NS",
    "MODERNINS": "515008.BO",
}

DRY_RUN = "--dry-run" in sys.argv
INCLUDE_TODAY = "--include-today" in sys.argv


def session_closed():
    now = datetime.now()
    return (now.hour, now.minute) >= MARKET_CLOSE


def read_meta(path):
    """(header, date_idx, static_prefix, dates, last_dt) for one CSV.

    static_prefix is every column before Date, carried from the first data row
    so appended rows stay byte-compatible with the ones already there.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return None
    header = rows[0]
    if "Date" not in header:
        return None
    di = header.index("Date")

    static, dates, last = None, set(), None
    for r in rows[1:]:
        if len(r) <= di or not r[di].strip():
            continue
        if static is None:
            static = r[:di]
        d = r[di].strip()
        dates.add(d)
        try:
            dt = datetime.strptime(d, DATE_FMT)
        except ValueError:
            continue
        if last is None or dt > last:
            last = dt
    if static is None or last is None:
        return None
    return header, di, static, dates, last


def ticker_for(header, static, di, fname):
    """Prefer the file's own Symbol column; fall back to the filename."""
    sym = None
    if "Symbol" in header:
        si = header.index("Symbol")
        if si < di and si < len(static):
            sym = static[si].strip()
    if not sym:
        sym = fname.replace("_1d_max.csv", "").replace(".csv", "")
    return sym


def fetch(sym, start_dt):
    start = (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    cands = [RENAMES[sym]] if sym in RENAMES else [sym + ".NS", sym + ".BO"]
    for tk in cands:
        try:
            df = yf.Ticker(tk).history(start=start, end=end, interval="1d",
                                       auto_adjust=True, actions=True)
        except Exception:
            continue
        if df is not None and not df.empty:
            return df, tk
    return None, None


def process_folder(folder, drop_today, today_str):
    # Absolute paths allowed so folders outside this checkout can be swept --
    # the ML Forecast pipeline's d:\PC2546\portfolio\NIFTY500 is one of them.
    # Its own updater (eod_update.py) reads Date from column 5, but that folder
    # puts Date at column 4, so every file errors and the folder silently never
    # updates. Header-driven parsing is what makes it work here.
    path = folder if os.path.isabs(folder) else os.path.join(MAIN, folder)
    if not os.path.isdir(path):
        print(f"[skip] {folder} not found")
        return 0, 0, 0, []
    files = sorted(f for f in os.listdir(path) if f.lower().endswith(".csv"))
    print(f"\n=== {folder} ({len(files)} CSVs) ===")

    updated = current = failed = 0
    rows_added = 0
    stale = []
    for i, fn in enumerate(files, 1):
        fp = os.path.join(path, fn)
        meta = read_meta(fp)
        if meta is None:
            print(f"  [{i:4}/{len(files)}] {fn:<28} UNREADABLE")
            failed += 1
            continue
        header, di, static, dates, last = meta
        sym = ticker_for(header, static, di, fn)

        df, used = fetch(sym, last)
        if df is None:
            stale.append((sym, last))
            failed += 1
            time.sleep(SLEEP_BETWEEN)
            continue

        new = []
        for idx, r in df.iterrows():
            ds = idx.strftime(DATE_FMT)
            if ds in dates:
                continue
            if drop_today and ds == today_str:
                continue
            # Close is the column everything downstream reads; a bar without one
            # is what put an empty Close into the index CSVs on 28-08.
            if r.get("Close") is None or r.get("Close") != r.get("Close"):
                continue
            new.append(static + [ds,
                                 str(r.get("Open", 0.0)), str(r.get("High", 0.0)),
                                 str(r.get("Low", 0.0)), str(r.get("Close", 0.0)),
                                 str(int(r.get("Volume", 0) or 0)),
                                 str(r.get("Dividends", 0.0)),
                                 str(r.get("Stock Splits", 0.0))])
            dates.add(ds)

        if new:
            if not DRY_RUN:
                with open(fp, "a", encoding="utf-8", newline="") as fh:
                    csv.writer(fh, lineterminator="\n").writerows(new)
            updated += 1
            rows_added += len(new)
            print(f"  [{i:4}/{len(files)}] {sym:<16} +{len(new)} "
                  f"({last:%d-%m-%Y} -> {new[-1][di]})  [{used}]")
        else:
            current += 1
        time.sleep(SLEEP_BETWEEN)

    print(f"  {folder}: updated {updated} | already current {current} | "
          f"no data {failed} | +{rows_added} rows")
    return updated, current, failed, stale


def verify(folder):
    """No duplicate dates, and what the folder now ends on."""
    path = folder if os.path.isabs(folder) else os.path.join(MAIN, folder)
    if not os.path.isdir(path):
        return
    dupes, last = [], {}
    for fn in sorted(f for f in os.listdir(path) if f.lower().endswith(".csv")):
        meta = read_meta(os.path.join(path, fn))
        if meta is None:
            continue
        header, di, _, dates, _ = meta
        with open(os.path.join(path, fn), encoding="utf-8", errors="replace") as fh:
            rows = list(csv.reader(fh))[1:]
        seen = [r[di].strip() for r in rows if len(r) > di and r[di].strip()]
        if len(seen) != len(set(seen)):
            dupes.append(fn)
        last[seen[-1]] = last.get(seen[-1], 0) + 1
    top = sorted(last.items(), key=lambda kv: -kv[1])[:3]
    print(f"  {folder:<24} duplicate-date files: {len(dupes)} | last bar: {dict(top)}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folders = [a for a in args if os.path.isabs(a)] or [f for f in FOLDERS if not args or f in args]
    unknown = [a for a in args if a not in FOLDERS and not os.path.isabs(a)]
    if unknown:
        sys.exit(f"[error] unknown folder(s): {', '.join(unknown)} "
                 f"(valid: {', '.join(FOLDERS)})")

    drop_today = not (INCLUDE_TODAY or session_closed())
    today_str = datetime.today().strftime(DATE_FMT)
    print(f"Stock updater — {datetime.now():%Y-%m-%d %H:%M:%S}")
    if drop_today:
        print(f"session still open - dropping partial bar for {today_str}")
    if DRY_RUN:
        print("DRY RUN - nothing will be written")

    all_stale = []
    for folder in folders:
        *_, stale = process_folder(folder, drop_today, today_str)
        all_stale += [(folder, s, d) for s, d in stale]

    if not DRY_RUN:
        print("\n=== verification ===")
        for folder in folders:
            verify(folder)

    if all_stale:
        print(f"\nno fresh data for {len(all_stale)} symbol(s):")
        for folder, s, d in all_stale[:40]:
            print(f"   {folder:<22} {s:<16} last {d:%d-%m-%Y}")
        if len(all_stale) > 40:
            print(f"   ... and {len(all_stale) - 40} more")


if __name__ == "__main__":
    main()
