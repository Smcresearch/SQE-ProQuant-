"""
update_bondyield.py
-------------------
Merge a fresh Investing.com 1-Year bond yield export into the risk-free files.

There are two of them and they are NOT the same file:
    d:\\Host_portfolio\\India 1-Year Bond Yield Historical Data.csv   SOM_hq_quarterly.py
    D:\\Shared folder\\portfolio\\bondyield.csv                        som_metals/-_ml/_hedge/_hq

Merge, never copy. Each target reaches further back than the export does (2008
and 2013 respectively, against the export's 2015), so overwriting would silently
amputate years of risk-free history -- and the SOM engines index RF by month, so
the loss would only surface as a wrong Sharpe on old months, not as an error.

Union on Date, the fresh export winning any overlapping day, newest row first
(the shape Investing.com exports and both readers expect).

    python update_bondyield.py                       # default export path
    python update_bondyield.py <path-to-export.csv>
"""
import os
import shutil
import sys
from datetime import datetime

import pandas as pd

DEFAULT_SRC = r"E:\VOFA\India 1-Year Bond Yield Historical Data.csv"
TARGETS = [
    r"d:\Host_portfolio\India 1-Year Bond Yield Historical Data.csv",
    r"D:\Shared folder\portfolio\bondyield.csv",
    # The ML Forecast pipeline (d:\PC2546\portfolio\ml_pipeline) keeps its own
    # copy. eod_update.py refreshes the NIFTY500 stock CSVs but explicitly does
    # NOT touch the bond or benchmark files, and the pipeline uses the latest
    # month present in ALL of stock+benchmark+bond -- so a stale copy here
    # silently pins the whole ML book to an older month.
    r"d:\PC2546\portfolio\bondyield.csv",
]
DATE_FMT = "%d-%m-%Y"


def load(path):
    # utf-8-sig: bondyield.csv carries a BOM, the other does not. Reading with
    # -sig handles both; writing it back preserves what each file already had.
    enc = "utf-8-sig" if open(path, "rb").read(3) == b"\xef\xbb\xbf" else "utf-8"
    df = pd.read_csv(path, encoding=enc)
    df["_d"] = pd.to_datetime(df["Date"], format=DATE_FMT)
    return df, enc


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    if not os.path.exists(src):
        sys.exit(f"[error] export not found: {src}")
    new, _ = load(src)
    print(f"export {len(new):5d} rows  {new['_d'].min():%d-%m-%Y} -> {new['_d'].max():%d-%m-%Y}")

    stamp = datetime.today().strftime("%Y%m%d")
    for target in TARGETS:
        if not os.path.exists(target):
            print(f"[skip] {target} not found")
            continue
        old, enc = load(target)
        merged = (pd.concat([new, old], ignore_index=True)
                    .drop_duplicates(subset="_d", keep="first")
                    .sort_values("_d", ascending=False))

        assert merged["_d"].is_unique, "duplicate dates survived the merge"
        assert len(merged) >= len(old), "merge lost rows vs the target"
        assert merged["_d"].min() == old["_d"].min(), "oldest row lost from the target"
        assert merged["_d"].max() == max(old["_d"].max(), new["_d"].max()), "newest row is wrong"
        assert merged["Price"].notna().all(), "null price in merged output"

        bak = f"{target}.bak-{stamp}"
        if not os.path.exists(bak):
            shutil.copy2(target, bak)
        merged.drop(columns="_d").to_csv(target, index=False, quoting=1, encoding=enc)
        print(f"{os.path.basename(target):<46} {len(old):5d} -> {len(merged):5d} rows  "
              f"({merged['_d'].min():%d-%m-%Y} -> {merged['_d'].max():%d-%m-%Y})  "
              f"+{len(merged) - len(old)}")


if __name__ == "__main__":
    main()
