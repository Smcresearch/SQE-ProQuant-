"""
update_sqe.py
-------------
Daily driver for the SQE dashboards, run after market close by the
"SQE Daily Price Update" scheduled task via run_daily_sqe_update.bat.

Rebuilt: the original was deleted along with the fetchers it called
(data_set_nifty5.py, data_set_nifty500.py, index_data.py, update_stocks.py,
extract_ml.py, extract_hq.py). None of them exist anywhere on this machine, so
this drives their replacements instead. The scheduled task has been failing
since 31-08-2026 with "can't open file update_sqe.py".

    [1] prices    every per-stock folder, both indices, the CNX500 benchmark
                  and the bullion sleeve, to the last completed session
    [2] rebuild   data.js / hq_data.js / ml_data.js / holdings.js
    [3] publish   sync into the two site checkouts, commit, push

Backtests are NOT run here -- they are monthly, and re-running them nightly
would rewrite the published book mid-month. Use run_hedge_backtests.py,
SOM_hq_quarterly.py and eod_update.py at the month roll.

Nothing is published if a price step fails: a half-refreshed set of CSVs
produces a book that looks plausible and is wrong.

    python update_sqe.py --prices        # the nightly job
    python update_sqe.py --no-push       # rebuild locally, publish nothing
    python update_sqe.py --dry-run       # print the plan and stop
"""
import os
import subprocess
import sys
from datetime import datetime

MAIN = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ML_DIR = os.environ.get("ML_PIPELINE_DIR", r"d:\PC2546\portfolio")

# (checkout, copy from MAIN, git add, label)
#
# ProQuant publishes from MAIN itself, NOT from d:\SQE-ProQuant-host. Both are
# checkouts of the same repo (Smcresearch/SQE-ProQuant-.git), and having two
# working copies commit to one remote is what killed this job on 30-08-2026 and
# again on 02-09-2026 -- "! [rejected] main -> main (fetch first)". MAIN is the
# right one to keep: it holds the tracked scripts as well as the site files, and
# it is where every data file is built, so publishing from it needs no copy step
# and cannot drift. d:\SQE-ProQuant-host is left as a read-only spare.
#
# The All-Indices holdings.js is written straight into its checkout by
# build_holdings.py, so it is staged but not copied.
SITES = [
    (r"d:\SQE-host", ["data.js"], ["data.js", "holdings.js"], "All-Indices"),
    (MAIN, [], ["data.js", "holdings.js", "hq_data.js", "ml_data.js", "index.html"],
     "ProQuant"),
]

DRY = "--dry-run" in sys.argv
NO_PUSH = "--no-push" in sys.argv


def run(cmd, cwd=MAIN, env=None, label=""):
    shown = " ".join(str(c) for c in cmd)
    print(f"    $ {shown}", flush=True)
    if DRY:
        return 0
    e = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if env:
        e.update(env)
    rc = subprocess.run(cmd, cwd=cwd, env=e).returncode
    if rc != 0:
        print(f"    [FAIL] rc={rc}  {label or shown}", flush=True)
    return rc


def step(title):
    print(f"\n[{title}]", flush=True)


def main():
    print("=" * 72)
    print(f"  SQE daily update  |  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 72)

    # ---- 1. prices -----------------------------------------------------
    step("1/3 prices")
    failed = []
    for cmd, label in [
        ([PY, "-u", "update_stocks.py"], "per-stock folders"),
        ([PY, "-u", "update_stocks.py", os.path.join(ML_DIR, "NIFTY500")],
         "ML Forecast universe"),
        ([PY, "-u", "update_indices.py"], "indices + CNX500"),
        ([PY, "-u", "update_bullion.py"], "GOLDBEES / SILVERBEES"),
    ]:
        if run(cmd, label=label) != 0:
            failed.append(label)

    if failed:
        print(f"\n[ABORT] price refresh failed: {', '.join(failed)}")
        print("[ABORT] nothing rebuilt or published -- a partially refreshed set "
              "of CSVs yields a book that looks right and is not.")
        return 1

    # ---- 2. rebuild ----------------------------------------------------
    step("2/3 rebuild")
    for cmd, label in [
        ([PY, "-u", "extract_dashboard_data.py"], "data.js"),
        ([PY, "-u", "build_hq_backtest_dashboard.py"], "hq_data.js"),
        ([PY, "-u", "extract_ml.py"], "ml_data.js"),
    ]:
        if run(cmd, label=label) != 0:
            failed.append(label)

    # holdings.js: one flat file for the All-Indices site, one keyed by universe
    # for ProQuant. build_holdings.py emits a single universe per run, so the
    # ProQuant file is assembled from three runs.
    scratch = os.path.join(MAIN, "scratch")
    os.makedirs(scratch, exist_ok=True)
    if run([PY, "-u", "build_holdings.py"],
           env={"HOLDINGS_SRC": "Hedge_Pro_Summary_759.xlsx",
                "HOLDINGS_OUT": r"d:/SQE-host/holdings.js"},
           label="holdings.js (All-Indices)") != 0:
        failed.append("holdings.js (All-Indices)")

    parts = {}
    for key, src in [("nifty50", "Hedge_nifty50.xlsx"),
                     ("nifty500", "Hedge_nifty500.xlsx"),
                     ("total759", "Hedge_Pro_Summary_759.xlsx")]:
        tmp = os.path.join(scratch, f"_holdings_{key}.js")
        if run([PY, "-u", "build_holdings.py"],
               env={"HOLDINGS_SRC": src, "HOLDINGS_OUT": tmp},
               label=f"holdings.js ({key})") != 0:
            failed.append(f"holdings.js ({key})")
        parts[key] = tmp

    if not DRY and not failed:
        import json
        merged = {}
        for key, tmp in parts.items():
            txt = open(tmp, encoding="utf-8").read()
            merged[key] = json.JSONDecoder().raw_decode(txt[txt.index("{"):])[0]
        with open(os.path.join(MAIN, "holdings.js"), "w", encoding="utf-8") as f:
            f.write("/* Per-month Base SIM holdings for the heatmap modal. "
                    "Auto-generated. */\n")
            f.write("const MONTHLY_HOLDINGS = "
                    + json.dumps(merged, separators=(",", ":"), ensure_ascii=False)
                    + ";\n")
        print(f"    [ok] holdings.js merged ({', '.join(merged)})")

    if failed:
        print(f"\n[ABORT] rebuild failed: {', '.join(failed)} -- not publishing.")
        return 1

    # ---- 3. publish ----------------------------------------------------
    step("3/3 publish")
    if NO_PUSH:
        print("    --no-push: rebuilt locally, nothing committed.")
        return 0

    import shutil
    stamp = f"{datetime.now():%Y-%m-%d %H:%M:%S} IST"
    for site, copy_files, add_files, label in SITES:
        if not os.path.isdir(site):
            print(f"    [skip] {label}: {site} not found")
            continue
        print(f"    {label} ({site})")
        if not DRY:
            for fn in copy_files:
                src = os.path.join(MAIN, fn)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(site, fn))
        run(["git", "add"] + add_files, cwd=site, label=f"{label} add")
        # Nothing staged on a holiday or a re-run -- that is not a failure.
        if not DRY:
            unchanged = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                       cwd=site).returncode == 0
            if unchanged:
                print("    [skip] no change to commit")
                continue
        if run(["git", "commit", "-m", f"data: daily price sync ({stamp})"],
               cwd=site, label=f"{label} commit") != 0:
            continue
        run(["git", "push", "origin", "main"], cwd=site, label=f"{label} push")

    print(f"\n[done] {datetime.now():%Y-%m-%d %H:%M:%S}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
