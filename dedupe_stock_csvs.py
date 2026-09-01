"""
Drop duplicate-date rows from the per-stock price CSVs.

The incremental updater can write a bar twice for the same session: once as an
intraday snapshot (partial high/low/close, low volume) and again after the
close with the settled values. The later row is the correct one, so for each
date we keep the LAST occurrence.

Duplicate dates are not harmless — a repeated date breaks any reindex on the
daily series (som_metals.py's drawdown build raises "cannot reindex on an axis
with duplicate labels") and double-counts a session in monthly resampling.

A backup of every modified file is written alongside it under _dupe_backup/.

Usage:
  python dedupe_stock_csvs.py --check      # report only, change nothing
  python dedupe_stock_csvs.py             # fix in place (with backup)
"""
import glob
import os
import shutil
import sys

import pandas as pd

MAIN = os.path.dirname(os.path.abspath(__file__))
# hq_quarterly_universe mixes both CSV shapes -- some files put Date at column 4
# (Symbol,Company,Industry,Index,Date,...) and some at column 5
# (Company,Industry,Symbol,Series,ISIN,Date,...). Selecting the column by NAME
# is what makes that safe to sweep alongside the others.
FOLDERS = ["nifty50_host", "nifty500_host", "TOTAL_STOCKS", "hq_quarterly_universe"]
BACKUP = os.path.join(MAIN, "_dupe_backup")


def main():
    check_only = "--check" in sys.argv
    # Extra folders can be named on the command line -- the High_Quality_* sets
    # live under the shared portfolio folder, not next to this script, and they
    # mix both CSV shapes just like hq_quarterly_universe does.
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folders = args or FOLDERS
    total_files = total_dropped = 0

    for folder in folders:
        path = folder if os.path.isabs(folder) else os.path.join(MAIN, folder)
        if not os.path.isdir(path):
            print(f"[skip] {folder} not found")
            continue

        hits = []
        for p in sorted(glob.glob(os.path.join(path, "*.csv"))):
            df = pd.read_csv(p)
            df.columns = [c.strip() for c in df.columns]
            if "Date" not in df.columns:
                continue
            dup = df["Date"].duplicated(keep="last")
            if not dup.any():
                continue
            hits.append((p, int(dup.sum()), sorted(set(df.loc[df["Date"].duplicated(keep=False), "Date"]))))
            if not check_only:
                # basename, not the raw folder: os.path.join drops BACKUP when
                # the second part is absolute, which made the backup path equal
                # the source and turned copy2 into a copy-onto-itself.
                dest = os.path.join(BACKUP, os.path.basename(os.path.normpath(folder)))
                os.makedirs(dest, exist_ok=True)
                shutil.copy2(p, os.path.join(dest, os.path.basename(p)))
                df[~dup].to_csv(p, index=False)

        dropped = sum(h[1] for h in hits)
        total_files += len(hits)
        total_dropped += dropped
        dates = sorted({d for h in hits for d in h[2]})
        print(f"{folder:16s} {len(hits):4d} files with duplicate dates, {dropped} rows"
              f"{'' if not dates else '  dates: ' + ', '.join(dates[:6])}")

    verb = "would drop" if check_only else "dropped"
    print(f"\n{verb} {total_dropped} duplicate rows across {total_files} files")
    if not check_only and total_files:
        print(f"originals backed up under {BACKUP}")


if __name__ == "__main__":
    main()
