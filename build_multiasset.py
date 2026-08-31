"""
Build the data file for the SQE MultiAsset ProQuant site (Equity + Gold + Silver).

The multi-asset numbers are produced by a DIFFERENT engine than the equity-only
SQE sites: `som_metals.py` in the shared portfolio folder runs the same EGP /
Sharpe single-index selection but reserves a FIXED slice of capital for the
bullion sleeve (GOLDBEES / SILVERBEES), so the stock sleeve is 1 - gold - silver.

  base        gold 0%   silver 0%   -> 100% stocks   (control)
  gold        gold 10%  silver 0%   ->  90% stocks
  silver      gold 0%   silver 10%  ->  90% stocks
  goldsilver  gold 10%  silver 10%  ->  80% stocks

Those runs are already backtested into Sharpe_Summary_{UNIV}_A_{VARIANT}.xlsx.
`bullion_report/extract_metrics.py` and `extract_holdings.py` recompute every
statistic from those workbooks into metrics.json / holdings.json — this script
just merges the two into the site's data.js. Nothing is recomputed here, so the
site can never disagree with the PDF report built from the same JSONs.

Window is 2022-06 -> 2026-04 (47 months), bounded by SILVERBEES inception
(2022-05-10). Every universe and variant uses the identical window so the
comparison is like-for-like.

Usage:
  python build_multiasset.py                    # merge existing JSONs -> data.js
  python build_multiasset.py --extract          # re-run the extractors first, then merge
  python build_multiasset.py --extract --push   # ... and commit + push the site

--extract is the one to use after a new month's backtests have been written to
the workbooks; the plain form just regenerates data.js from whatever the
extractors last produced.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

MAIN = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.environ.get(
    "BULLION_REPORT", r"D:\Shared folder\portfolio\bullion_report")
OUT_FILE = os.environ.get(
    "MULTIASSET_OUT", r"d:\SQE-MultiAsset-ProQuant-host\data.js")

UNIVERSES = [
    {"key": "N50",  "name": "Nifty 50",    "bench": "Nifty 50"},
    {"key": "N500", "name": "Nifty 500",   "bench": "Nifty 500"},
    {"key": "T759", "name": "All Indices", "bench": "Nifty 500"},
    {"key": "HQ",   "name": "High Quality", "bench": "Nifty 500"},
]
VARIANTS = [
    {"key": "base",       "name": "Equity Only",           "short": "Equity",
     "gold": 0.00, "silver": 0.00, "color": "#64748b"},
    {"key": "gold",       "name": "Equity + Gold",         "short": "+Gold",
     "gold": 0.10, "silver": 0.00, "color": "#f4b942"},
    {"key": "silver",     "name": "Equity + Silver",       "short": "+Silver",
     "gold": 0.00, "silver": 0.10, "color": "#9fb3c8"},
    {"key": "goldsilver", "name": "Equity + Gold + Silver", "short": "+Gold+Silver",
     "gold": 0.10, "silver": 0.10, "color": "#22d3ee"},
]


def main():
    if "--extract" in sys.argv:
        print("[1] Re-running the extractors ...")
        # extract_monthly_holdings.py reads metrics.json, so it must run last.
        for script in ("extract_metrics.py", "extract_holdings.py",
                       "extract_monthly_holdings.py"):
            print(f"   -> {script}")
            subprocess.run([sys.executable, script], cwd=REPORT_DIR, check=True)
    else:
        print("[1] Using the existing metrics.json / holdings.json "
              "(pass --extract to rebuild them from the workbooks).")

    metrics_path = os.path.join(REPORT_DIR, "metrics.json")
    holdings_path = os.path.join(REPORT_DIR, "holdings.json")
    monthly_path = os.path.join(REPORT_DIR, "holdings_monthly.json")
    for p in (metrics_path, holdings_path, monthly_path):
        if not os.path.exists(p):
            sys.exit(f"[error] missing {p} — run with --extract first")

    with open(metrics_path, encoding="utf-8") as fh:
        metrics = json.load(fh)
    with open(holdings_path, encoding="utf-8") as fh:
        holdings = json.load(fh)
    with open(monthly_path, encoding="utf-8") as fh:
        monthly_books = json.load(fh)

    payload = {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "window": metrics["window"],
            "universes": UNIVERSES,
            "variants": VARIANTS,
            "sleeve_note": ("Bullion is held at a fixed weight of total capital and "
                            "rebalanced monthly with the equity basket. The stock "
                            "sleeve is whatever is left over."),
        },
        # The in-progress month, if any. Deliberately NOT merged into `monthly`:
        # a part-month must never reach an annualised statistic.
        "live": metrics.get("live"),
        "runs": metrics["runs"],
        "monthly": metrics["monthly"],
        "bullion": metrics["bullion"],
        "bullion_bh": metrics["bullion_bh"],
        "bullion_full_history": metrics["bullion_full_history"],
        "bullion_monthly": metrics["bullion_monthly"],
        "corr_matrix": metrics["corr_matrix"],
        "corr_matrix_traded": metrics["corr_matrix_traded"],
        "crisis": metrics["crisis"],
        "holdings": holdings,
    }

    # Sanity: every universe x variant must be present, and a universe's own
    # 4 variants (base/gold/silver/goldsilver) must share an identical window
    # -- that's the comparison that actually needs to be apples-to-apples.
    # Windows are NOT required to match ACROSS universes: HQ's fundamental
    # screen only has data back to 2023-07 (Screener.in scrape depth), while
    # the equity-only universes go back to 2022-06 (bounded by SILVERBEES
    # inception) -- a real, understood difference, not a bug.
    for u in UNIVERSES:
        u_months = None
        for v in VARIANTS:
            k = f"{u['key']}_{v['key']}"
            if k not in payload["runs"]:
                sys.exit(f"[error] run {k} missing from metrics.json")
            m = payload["runs"][k]["months"]
            if u_months is None:
                u_months = m
            elif m != u_months:
                sys.exit(f"[error] run {k} covers {m} months, expected {u_months} "
                         f"(to match {u['key']}'s other variants) — variant windows "
                         f"within one universe must match for a fair comparison")

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write("/* Generated by build_multiasset.py — do not edit by hand. */\n")
        fh.write("const MULTIASSET_DATA = ")
        json.dump(payload, fh, separators=(",", ":"), default=float)
        fh.write(";\n")

    # Per-month books ship separately: they are the bulk of the payload and only
    # the heatmap drill-down needs them.
    books_file = os.path.join(os.path.dirname(OUT_FILE), "holdings.js")
    with open(books_file, "w", encoding="utf-8") as fh:
        fh.write("/* Generated by build_multiasset.py — do not edit by hand. */\n")
        for name, obj in (("MONTHLY_HOLDINGS", monthly_books["holdings"]),
                          ("MONTH_META", monthly_books["meta"]),
                          ("SECTOR_MAP", monthly_books["sectors"])):
            fh.write(f"const {name} = ")
            json.dump(obj, fh, separators=(",", ":"), default=float)
            fh.write(";\n")

    w = metrics["window"]
    print(f"[2] Wrote {OUT_FILE}")
    print(f"    {len(payload['runs'])} runs, {w['months']} completed months "
          f"({w['first']} -> {w['last']}), {len(holdings)} current books")
    if payload["live"]:
        print(f"    live month {payload['live']['month']} (month-to-date as of "
              f"{payload['live']['as_of']}) reported separately")
    n_books = sum(len(v) for v in monthly_books["holdings"].values())
    print(f"    Wrote {books_file}")
    print(f"    {n_books} month-books across {len(monthly_books['holdings'])} runs, "
          f"{len(monthly_books['sectors'])} symbols classified")

    if "--push" in sys.argv:
        site = os.path.dirname(OUT_FILE)
        if not os.path.isdir(os.path.join(site, ".git")):
            sys.exit(f"[error] {site} is not a git repo — cannot push")
        print(f"[3] Pushing the site ({site}) ...")
        # holdings.js is regenerated alongside data.js above, so it has to be
        # staged with it — staging data.js alone lets the heatmap drill-down
        # drift out of sync with the headline numbers it belongs to.
        subprocess.run(["git", "add", "data.js", "holdings.js"], cwd=site, check=True)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=site).returncode
        if staged == 0:
            print("    No changes — site already up to date.")
            return
        subprocess.run(["git", "commit", "-m",
                        f"data: refresh multi-asset data ({w['first']} -> {w['last']}, "
                        f"{w['months']} months)"], cwd=site, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=site, check=True)
        print("    [OK] pushed.")


if __name__ == "__main__":
    main()
