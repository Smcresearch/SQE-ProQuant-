"""
run_hedge_backtests.py
----------------------
Produce the three Hedge books (Nifty 50 / Nifty 500 / All-Indices-759) that
feed data.js, for one signal month.

som_hedge.py has no CLI: every setting is a module-level constant and all the
work runs under `if __name__ == '__main__'`, so importing it and reassigning
does nothing. The books were previously made by editing those constants by hand
per universe. This does the same edit mechanically, on a throwaway copy, leaving
the engine itself untouched.

The per-universe config below is not guessed. Each book stores its realised
benchmark return per month, so the benchmark was identified by scoring the
stored series against every candidate CSV:

    Hedge_nifty50           NIFTY50_1d.csv       mean|err| 0.000190   corr 0.99962
    Hedge_nifty500          NSE_CNX500, 1D.csv   mean|err| 0.000008   corr 1.00000
    Hedge_Pro_Summary_759   NSE_CNX500, 1D.csv   mean|err| 0.000008   corr 1.00000

START_MONTH comes from the first Port_ sheet in each book (2020-01).

END_MONTH is the last TRADE month, NOT the signal month -- som_metals.py (driven
by run_multiasset_backtests.py) uses the opposite convention, so this is easy to
get backwards. som_hedge.py's own sheet header settles it:

    "PORTFOLIO FOR 2026-07 (Based on 2026-06 Data)"

A month whose price data is complete becomes a Port_ sheet; the last month whose
trade data is still incomplete becomes LIVE_PERF_ instead. That is why the
previous books look like Port_2020-01..Port_2026-07 + LIVE_PERF_2026-08 -- they
were run with END_MONTH=2026-08 while August was still incomplete.

So the September book is --end 2026-09, which yields Port_ through 2026-08 plus
LIVE_PERF_2026-09. Running --end 2026-08 now that August is complete produces
Port_2026-08 and NO LIVE_PERF sheet at all, which leaves
extract_dashboard_data.py with no current_portfolio to read.

    python run_hedge_backtests.py --end 2026-09          # all three
    python run_hedge_backtests.py --end 2026-09 nifty50  # just one
    python run_hedge_backtests.py --end 2026-09 --dry-run
"""
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

MAIN = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("PORTFOLIO_SHARED", r"D:\Shared folder\portfolio")
ENGINE = os.path.join(SHARED, "som_hedge.py")
BACKUP = os.path.join(MAIN, "_book_backup")

START_MONTH = "2020-01"

# name -> (stocks folder under MAIN, benchmark csv, summary out, deep-dive out)
# The output names are the ones extract_dashboard_data.py reads (its SOURCES
# table), not som_hedge.py's "_selected" defaults.
UNIVERSES = {
    "nifty50": ("nifty50_host", os.path.join(MAIN, "NIFTY50_1d.csv"),
                "Hedge_nifty50.xlsx", "Hedge_Institutional_Deep_Dive_nifty50.xlsx"),
    "nifty500": ("nifty500_host", os.path.join(SHARED, "NSE_CNX500, 1D.csv"),
                 "Hedge_nifty500.xlsx", "Hedge_Institutional_Deep_Dive_nifty500.xlsx"),
    "total759": ("TOTAL_STOCKS", os.path.join(SHARED, "NSE_CNX500, 1D.csv"),
                 "Hedge_Pro_Summary_759.xlsx", "Hedge_Institutional_Deep_Dive_759.xlsx"),
}


def rewrite(src, subs):
    """Replace every top-level `NAME = ...` assignment listed in subs.

    Every occurrence, not the first: som_hedge.py assigns OUTPUT_FILE,
    START_MONTH and END_MONTH twice (lines 27/30/31 then 40/44/45) and the
    later pair is what the engine actually uses. Rewriting only the first
    would leave the real values untouched.
    """
    out = src
    for name, value in subs.items():
        pattern = re.compile(rf"^{name}\s*=.*$", re.M)
        if not pattern.search(out):
            sys.exit(f"[error] constant {name} not found in {ENGINE}")
        # Callable replacement, not a string: re.sub interprets backslash
        # escapes in a string replacement, so repr()'s doubled backslashes in a
        # Windows path collapse back to single ones and the generated file dies
        # with "malformed \N character escape".
        line = f"{name} = {value!r}"
        out = pattern.sub(lambda _m, _l=line: _l, out)
    return out


def main():
    argv = sys.argv[1:]
    end = None
    names = []
    i = 0
    while i < len(argv):
        if argv[i] == "--end":
            end = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            names.append(argv[i])
            i += 1
    if not end:
        sys.exit("[error] --end YYYY-MM is required (the last SIGNAL month; "
                 "the book is traded the month after)")
    dry = "--dry-run" in argv
    unknown = [n for n in names if n not in UNIVERSES]
    if unknown:
        sys.exit(f"[error] unknown universe(s): {', '.join(unknown)} "
                 f"(valid: {', '.join(UNIVERSES)})")
    todo = names or list(UNIVERSES)

    if not os.path.exists(ENGINE):
        sys.exit(f"[error] engine not found: {ENGINE}")
    src = open(ENGINE, encoding="utf-8").read()

    print(f"signal months {START_MONTH} -> {end}  (books traded the month after {end})")
    stamp = datetime.today().strftime("%Y%m%d")

    failed = []
    for name in todo:
        folder, bench, summary, deep = UNIVERSES[name]
        stocks = os.path.join(MAIN, folder)
        for p, what in ((stocks, "stocks folder"), (bench, "benchmark")):
            if not os.path.exists(p):
                sys.exit(f"[error] {what} missing for {name}: {p}")

        subs = {
            "STOCKS_FOLDER": stocks,
            "BENCHMARK_FILE": bench,
            "START_MONTH": START_MONTH,
            "END_MONTH": end,
            "OUTPUT_FILE": os.path.join(MAIN, summary),
            "DEEP_DIVE_FILE": os.path.join(MAIN, deep),
        }
        print(f"\n=== {name} ===")
        for k, v in subs.items():
            print(f"    {k:<16} {v}")
        if dry:
            continue

        # The live book is what the site serves -- keep a copy before replacing it.
        for out in (summary, deep):
            p = os.path.join(MAIN, out)
            if os.path.exists(p):
                os.makedirs(BACKUP, exist_ok=True)
                bak = os.path.join(BACKUP, f"{out}.bak-{stamp}")
                if not os.path.exists(bak):
                    shutil.copy2(p, bak)

        # Written into SHARED so the engine's own relative reads -- bondyield.csv,
        # spot_parquet, futures_parquet -- still resolve as they always did.
        tmp = os.path.join(SHARED, f"_run_hedge_{name}.py")
        open(tmp, "w", encoding="utf-8").write(rewrite(src, subs))
        log = os.path.join(MAIN, "scratch", f"hedge_{name}_{end}.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        t = time.time()
        print(f"    running ... (log: {log})", flush=True)
        with open(log, "w", encoding="utf-8") as fh:
            rc = subprocess.run([sys.executable, "-u", tmp], cwd=SHARED,
                                stdout=fh, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
        os.remove(tmp)
        if rc == 0:
            print(f"    ok ({time.time() - t:.0f}s) -> {summary}")
        else:
            print(f"    FAILED rc={rc} -- see {log}")
            failed.append(name)

    if failed:
        print(f"\nfailed: {', '.join(failed)}")
        sys.exit(1)
    if not dry:
        print(f"\nprevious books backed up under {BACKUP}")


if __name__ == "__main__":
    main()
