"""
run_hq_multiasset.py
--------------------
Produce the four High Quality bullion variants the MultiAsset site needs:

    Sharpe_Summary_HQ_A_{base,gold,silver,goldsilver}.xlsx   (+ screener/current)

build_multiasset.py expects FOUR universes -- N50, N500, T759 and HQ -- but
run_multiasset_backtests.py only knows the first three, because those come from
som_metals.py while HQ comes from SOM_hq_quarterly.py. Nothing regenerated the
HQ set, so it stayed frozen at the 31-08-2026 build and never gained a live
month: the site's Sep 2026 panel showed "-" for all four HQ variants and for its
benchmark, while GOLDBEES and SILVERBEES still printed because those are read
straight off the bullion CSVs rather than out of a workbook.

SOM_hq_quarterly.py already takes the sleeve weights and the output paths from
the environment, so each variant is just a different GOLD_WEIGHT/SILVER_WEIGHT.

    python run_hq_multiasset.py              # all four
    python run_hq_multiasset.py --dry-run
    python run_hq_multiasset.py goldsilver   # just one
"""
import os
import subprocess
import sys
import time

MAIN = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("PORTFOLIO_SHARED", r"D:\Shared folder\portfolio")
ENGINE = os.path.join(MAIN, "SOM_hq_quarterly.py")

# name -> (gold weight, silver weight). Same sleeve sizes as the equity
# universes use in run_multiasset_backtests.py.
VARIANTS = {
    "base": (0.00, 0.00),
    "gold": (0.10, 0.00),
    "silver": (0.00, 0.10),
    "goldsilver": (0.10, 0.10),
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    unknown = [a for a in args if a not in VARIANTS]
    if unknown:
        sys.exit(f"[error] unknown variant(s): {', '.join(unknown)} "
                 f"(valid: {', '.join(VARIANTS)})")
    todo = args or list(VARIANTS)

    if not os.path.exists(ENGINE):
        sys.exit(f"[error] engine not found: {ENGINE}")

    print(f"{len(todo)} HQ variant(s) -> {SHARED}")
    t0 = time.time()
    failed = []
    for i, name in enumerate(todo, 1):
        gold, silver = VARIANTS[name]
        tag = f"HQ_A_{name}"
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "GOLD_WEIGHT": str(gold),
            "SILVER_WEIGHT": str(silver),
            "OUTPUT_FILE": os.path.join(SHARED, f"Sharpe_screener_{tag}.xlsx"),
            "SUMMARY_ONLY_FILE": os.path.join(SHARED, f"Sharpe_Summary_{tag}.xlsx"),
            "CURRENT_PORT_FILE": os.path.join(SHARED, f"Current_Portfolio_{tag}.xlsx"),
        }
        print(f"[{i}/{len(todo)}] {tag:<20} gold={gold:.0%} silver={silver:.0%} ... ",
              end="", flush=True)
        if dry:
            print("(dry run)")
            continue
        log = os.path.join(MAIN, "scratch", f"hq_multiasset_{name}.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        t = time.time()
        # cwd=MAIN so the engine's relative inputs (hq_quarterly_universe, the
        # bond file, NIFTY500_1d.csv) resolve exactly as they do on its own run.
        with open(log, "w", encoding="utf-8") as fh:
            rc = subprocess.run([sys.executable, "-u", ENGINE], cwd=MAIN, env=env,
                                stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc == 0:
            print(f"ok ({time.time() - t:.0f}s)")
        else:
            print(f"FAILED rc={rc} -- see {log}")
            failed.append(tag)

    if not dry:
        print(f"\nDone in {(time.time() - t0) / 60:.1f} min. "
              f"{len(todo) - len(failed)}/{len(todo)} succeeded.")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
