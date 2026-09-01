"""
Run the 12 multi-asset backtests that feed the SQE MultiAsset ProQuant site:
3 universes x 4 bullion sleeves, all over one common window.

Each run invokes som_metals.py in the shared portfolio folder (it resolves
bondyield.csv and the two bullion CSVs relative to its own directory) but
points --stocks / --bench at THIS folder's price data, which the daily pipeline
keeps current. Outputs land next to the engine as
Sharpe_Summary_{UNIV}_A_{VARIANT}.xlsx, which is what the report extractors read.

END_MONTH is the last SIGNAL month. Its trade month is END_MONTH + 1, so
--end 2026-06 produces a book formed on the June close and held through July —
the live month.

Usage:
  python run_multiasset_backtests.py                 # all 12
  python run_multiasset_backtests.py N50 N500        # only these universes
  python run_multiasset_backtests.py --end 2026-06   # override the signal month
"""
import os
import subprocess
import sys
import time
from datetime import date, timedelta

MAIN = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("PORTFOLIO_SHARED", r"D:\Shared folder\portfolio")
# Where the stock folders / benchmark CSVs are read from. Defaults to this
# folder (the live price data). Point it at an as-of snapshot to reproduce a
# book formed on an earlier cutoff — e.g. the August baskets were built on the
# Jul 30 close, before Jul 31 existed.
DATA_ROOT = os.environ.get("MULTIASSET_DATA_ROOT", MAIN)

START_MONTH = "2022-05"     # first signal month -> first trade month 2022-06
# Last SIGNAL month = the last CALENDAR month that has closed. Hardcoding it
# froze the live month the moment the calendar rolled over: the nightly job kept
# re-marking a stale book instead of forming the new one. --end still overrides.
_t = date.today().replace(day=1) - timedelta(days=1)
END_MONTH = _t.strftime("%Y-%m")   # e.g. 2026-07 -> live trade month 2026-08

UNIVERSES = [
    ("N50",  "nifty50_host",  "NIFTY50_1d.csv"),
    ("N500", "nifty500_host", "NIFTY500_1d.csv"),
    ("T759", "TOTAL_STOCKS",  "NIFTY500_1d.csv"),
]
VARIANTS = [
    ("base",       0.00, 0.00),
    ("gold",       0.10, 0.00),
    ("silver",     0.00, 0.10),
    ("goldsilver", 0.10, 0.10),
]


def main():
    # Positional args are universe filters. Drop the flags AND their values,
    # otherwise "--end 2026-07" leaves "2026-07" looking like a universe name,
    # which silently matches nothing and runs zero backtests.
    end = END_MONTH
    argv = sys.argv[1:]
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--end":
            end = argv[i + 1] if i + 1 < len(argv) else end
            i += 2
        elif argv[i].startswith("--"):
            i += 1
        else:
            args.append(argv[i])
            i += 1
    universes = [u for u in UNIVERSES if not args or u[0] in args]
    unknown = [a for a in args if a not in {u[0] for u in UNIVERSES}]
    if unknown:
        sys.exit(f"[error] unknown universe(s): {', '.join(unknown)} "
                 f"(valid: {', '.join(u[0] for u in UNIVERSES)})")

    jobs = [(u, folder, bench, v, g, s)
            for u, folder, bench in universes
            for v, g, s in VARIANTS]
    if not jobs:
        sys.exit("[error] no runs selected — nothing to do")
    print(f"{len(jobs)} runs, signal months {START_MONTH} -> {end} "
          f"(live trade month follows {end})\n")

    t0 = time.time()
    failed = []
    for i, (u, folder, bench, v, g, s) in enumerate(jobs, 1):
        tag = f"{u}_A_{v}"
        cmd = [sys.executable, "-u", "som_metals.py",
               "--gold", str(g), "--silver", str(s),
               "--start", START_MONTH, "--end", end, "--tag", tag,
               "--stocks", os.path.join(DATA_ROOT, folder),
               "--bench", os.path.join(DATA_ROOT, bench)]
        t = time.time()
        print(f"[{i}/{len(jobs)}] {tag:20s} stocks={folder:14s} gold={g:.0%} silver={s:.0%} ... ",
              end="", flush=True)
        log = os.path.join(MAIN, "scratch", f"multiasset_{tag}.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w", encoding="utf-8") as fh:
            rc = subprocess.run(cmd, cwd=SHARED, stdout=fh, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
        if rc == 0:
            print(f"ok ({time.time() - t:.0f}s)")
        else:
            print(f"FAILED rc={rc} -- see {log}")
            failed.append(tag)

    print(f"\nDone in {(time.time() - t0) / 60:.1f} min. "
          f"{len(jobs) - len(failed)}/{len(jobs)} succeeded.")
    if failed:
        print("failed:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
