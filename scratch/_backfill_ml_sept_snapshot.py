"""One-off: put the September book back into MONTHLY_HOLDINGS.ml_forecast.

extract_ml.py carried MONTHLY_HOLDINGS forward verbatim on every run, so the ML
tab's snapshot froze at trade month 2026-08. extract_ml.py now writes the
current month each run, which fixes it going forward, but 2026-09 was skipped
while the bug was live and the run that produced that book is gone -- the
pipeline is stochastic and its workbooks have since been overwritten.

The September book does survive in the ml_data.js that was published on
30-09-2026 (commit f857763), so it is recovered from there. Run once.

    python scratch/_backfill_ml_sept_snapshot.py
"""
import json
import os
import re
import subprocess
import sys

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML_DATA_JS = os.path.join(MAIN, "ml_data.js")
REV = "f857763"            # the 30-09-2026 publish, which carried the Sept book
MONTH = "2026-09"
CAPITAL = 10_000_000


def payload_at(rev):
    txt = subprocess.run(["git", "show", f"{rev}:ml_data.js"], cwd=MAIN,
                         capture_output=True, text=True, encoding="utf-8").stdout
    m = re.search(r"DASHBOARD_DATA\.ml_forecast\s*=\s*", txt)
    if not m:
        sys.exit(f"[error] no ml_forecast payload in {rev}:ml_data.js")
    return json.JSONDecoder().raw_decode(txt[txt.index("{", m.end() - 1):])[0]


def main():
    sept = payload_at(REV)["current_portfolio"]
    rows = []
    for h in sept:
        q = h.get("qty") or 0
        w = h.get("weight") or 0.0
        # Formation price, as build_holdings.py derives it: weight * capital / qty.
        # The published row carries ltp (a live price), not the sizing price.
        p = (w * CAPITAL / q) if q else None
        rows.append({"s": h["clean_symbol"], "sec": h.get("sector") or "Other",
                     "w": round(w * 100, 2),
                     "p": round(p, 2) if p else None,
                     "r": None,                     # filled from October's prices
                     "st": "Added" if not h.get("prev_qty") else "Remained",
                     "a": h.get("action") or "—",
                     "b": None, "e": None})         # that run's PM sheet is gone
    rows.sort(key=lambda x: -(x["w"] or 0))

    txt = open(ML_DATA_JS, encoding="utf-8").read()
    m = re.search(r"MONTHLY_HOLDINGS\.ml_forecast\s*=\s*", txt)
    if not m:
        sys.exit("[error] ml_data.js has no MONTHLY_HOLDINGS.ml_forecast")
    start = txt.index("{", m.end() - 1)
    obj, length = json.JSONDecoder().raw_decode(txt[start:])
    if MONTH in obj:
        print(f"[skip] {MONTH} already present ({len(obj[MONTH])} names)")
        return
    obj[MONTH] = rows
    obj = {k: obj[k] for k in sorted(obj)}
    out = (txt[:start]
           + json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
           + txt[start + length:])
    open(ML_DATA_JS, "w", encoding="utf-8").write(out)
    print(f"[ok] inserted {MONTH} with {len(rows)} names "
          f"({', '.join(r['s'] for r in rows[:5])}...)")
    print(f"     MONTHLY_HOLDINGS.ml_forecast now {len(obj)} months, "
          f"{min(obj)} .. {max(obj)}")


if __name__ == "__main__":
    main()
