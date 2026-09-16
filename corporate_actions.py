"""
corporate_actions.py
--------------------
Back-adjust the per-stock CSVs for splits and bonus issues.

A bulk yfinance fetch returns a fully split-adjusted series, so the CSVs were
correct the day they were created. update_stocks.py only APPENDS the newest
session, though, and nothing rescales what is already on disk. So when a stock
goes ex-bonus the new bar arrives at the new price while every older bar keeps
the old one, and the step reads downstream as a real move:

    PGIL 1:1 bonus, ex 11-09-2026   2378.40 -> 1187.70
    live_prices.py / extract_dashboard_data.py both take the last two closes
    -> -50.06% for the day, -51.79% MTD, on every dashboard that renders it.

The ex-date row carries the factor in its "Stock Splits" column (2.0 for 1:1),
which is the signal used here. yfinance does not always stamp it on the right
bar -- TRENT's 3:2 bonus traded ex on 03-06-2026 but is flagged on 29-05 and
again on 04-06 -- so the flag only says "a split happened around here" and the
matching price step is what says where. A file is already adjusted when no such
step is left, which is why this is safe to re-run.

Adjusting = divide every OHLC before the ex-date by the factor, multiply Volume
by it. Cells after the ex-date, and every other column, are left byte-identical.

    python corporate_actions.py --dry-run          # report, write nothing
    python corporate_actions.py                    # all price folders
    python corporate_actions.py TOTAL_STOCKS       # only these
"""
import csv
import math
import os
import sys

MAIN = os.path.dirname(os.path.abspath(__file__))
FOLDERS = ["TOTAL_STOCKS", "nifty50_host", "nifty500_host", "hq_quarterly_universe"]

# How far from the flagged bar the matching price step may sit, and how far the
# step may be from the factor itself -- the ex-date bar still trades, so a clean
# 2:1 lands somewhere near 2.0 rather than on it.
WINDOW = 5
TOL = math.log(1.08)
# Below roughly 1:5 the ex-date drop is the size of an ordinary bad day and the
# flag alone cannot tell them apart: KTKBANK carries a 1.1 flag on 17-03-2020,
# in the middle of the COVID crash, on a series that is already adjusted.
# Missing a small bonus costs one wrong day on the dashboard; acting on a false
# positive silently rescales twenty years of history.
MIN_FACTOR = 1.2
# Bars each side of a candidate. The step has to be a level shift that STICKS:
# 1990s yfinance data is littered with runs that sit exactly on the split factor
# and then fall back (LT halves for one bar on 27-09-2006, CIPLA jumps 5x for
# one on 11-05-2004, RELIANCE runs 2x for seven bars from 27-10-1997). Comparing
# medians over a horizon longer than those runs is what tells a corporate action
# from bad prints. It only has to confirm the shift is still there, so its
# tolerance is loose -- a month of ordinary trading moves the median too.
SIDE = 20
HOLD_TOL = math.log(1.25)

DRY_RUN = "--dry-run" in sys.argv


def _cols(header):
    """Column indices by name, or None if this file is not a price CSV."""
    ix = {c.strip().lower(): i for i, c in enumerate(header)}
    need = ["date", "open", "high", "low", "close", "volume", "stock splits"]
    if any(c not in ix for c in need):
        return None
    return {c: ix[c] for c in need}


def _num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _median(xs):
    xs = sorted(x for x in xs if x and x > 0)
    return xs[len(xs) // 2] if xs else None


def _step_at(close, j):
    """Level shift across bar j: median of the closes before it over the median
    from it onwards. A one-bar spike moves neither median."""
    lo = _median(close[max(0, j - SIDE):j])
    hi = _median(close[j:j + SIDE])
    return lo / hi if lo and hi else None


def _find_step(close, i, factor):
    """Index of the bar whose level shift best matches `factor`, searched around
    the flagged bar `i`. None when the history is already adjusted -- then no
    step near the flag is anything but ~1.0."""
    if factor < MIN_FACTOR:
        return None
    lf = math.log(factor)
    best, best_gap = None, 0.0
    for j in range(max(1, i - WINDOW), min(len(close), i + WINDOW + 1)):
        prev, cur = close[j - 1], close[j]
        if not prev or not cur or cur <= 0:
            continue
        # The overnight gap pins the ex-date, and pins it precisely: an
        # unadjusted split is one bar where the close divides by the factor.
        gap = prev / cur
        if abs(math.log(gap) - lf) > TOL:
            continue
        # ...but a bad print is also one bar. Only a corporate action still
        # shows the shift a month either side.
        held = _step_at(close, j)
        if not held or abs(math.log(held) - lf) > HOLD_TOL:
            continue
        if gap > best_gap:
            best, best_gap = j, gap
    return best


def scan(path):
    """[(ex_row, date, factor, observed_step)] still to be applied to this CSV."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 3:
        return [], rows, None
    ix = _cols(rows[0])
    if ix is None:
        return [], rows, None

    body = rows[1:]
    close = [_num(r[ix["close"]]) if len(r) > ix["close"] else None for r in body]
    pending = []
    for i, r in enumerate(body):
        if len(r) <= ix["stock splits"]:
            continue
        f = _num(r[ix["stock splits"]])
        if not f or f <= 0 or abs(f - 1.0) < 1e-9:
            continue
        j = _find_step(close, i, f)
        if j is None:
            continue
        pending.append((j, body[i][ix["date"]], f, _step_at(close, j)))
        # Apply to the working copy so a second flag for the SAME event -- which
        # is how TRENT's 3:2 shows up -- no longer finds a step and is skipped.
        for k in range(j):
            if close[k]:
                close[k] /= f
    return pending, rows, ix


def adjust(path):
    """Apply every pending split to one CSV. Returns what was applied."""
    pending, rows, ix = scan(path)
    if not pending:
        return []
    if DRY_RUN:
        return pending

    # divisor[r] = product of the factors of every split that is still ahead of
    # row r, so overlapping adjustments compound instead of overwriting.
    body = rows[1:]
    divisor = [1.0] * len(body)
    for ex_row, _date, f, _step in pending:
        for k in range(ex_row):
            divisor[k] *= f

    for k, d in enumerate(divisor):
        if d == 1.0:
            continue
        r = body[k]
        for c in ("open", "high", "low", "close"):
            v = _num(r[ix[c]]) if len(r) > ix[c] else None
            if v is not None:
                r[ix[c]] = repr(v / d)
        v = _num(r[ix["volume"]]) if len(r) > ix["volume"] else None
        if v is not None:
            r[ix["volume"]] = str(int(round(v * d)))

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    os.replace(tmp, path)
    return pending


def main():
    folders = [a for a in sys.argv[1:] if not a.startswith("--")] or FOLDERS
    total = 0
    for folder in folders:
        path = folder if os.path.isabs(folder) else os.path.join(MAIN, folder)
        if not os.path.isdir(path):
            print(f"[skip] {folder} not found")
            continue
        files = sorted(f for f in os.listdir(path) if f.lower().endswith(".csv"))
        hits = 0
        for fn in files:
            for _row, date, f, step in adjust(os.path.join(path, fn)):
                hits += 1
                print(f"  {'[dry] ' if DRY_RUN else ''}{folder}/{fn:<28} "
                      f"ex {date}  split {f:g}  step {step:.3f}")
        print(f"=== {folder}: {len(files)} CSVs | {hits} split(s) "
              f"{'to apply' if DRY_RUN else 'applied'}")
        total += hits
    print(f"\n{total} adjustment(s) {'pending' if DRY_RUN else 'written'}")
    return 0


def _selftest():
    """Un-adjusted 1:1 gets halved; re-running changes nothing; a series that is
    already adjusted is left alone."""
    import tempfile
    hdr = "Symbol,Date,Open,High,Low,Close,Volume,Dividends,Stock Splits"
    raw = ["X,08-09-2026,200,200,200,200,100,0.0,0.0",
           "X,09-09-2026,210,210,210,210,100,0.0,0.0",
           "X,10-09-2026,220,220,220,220,100,0.0,0.0",
           "X,11-09-2026,110,110,110,110,300,0.0,2.0"]
    d = tempfile.mkdtemp()

    p = os.path.join(d, "a.csv")
    open(p, "w").write("\n".join([hdr] + raw) + "\n")
    assert len(adjust(p)) == 1
    out = [l.split(",") for l in open(p).read().strip().splitlines()[1:]]
    assert [float(r[5]) for r in out] == [100.0, 105.0, 110.0, 110.0], out
    assert [int(r[6]) for r in out] == [200, 200, 200, 300], out
    assert adjust(p) == [], "second run must be a no-op"

    # Flag one bar early, step one bar late -- the TRENT shape.
    p2 = os.path.join(d, "b.csv")
    shifted = ["X,08-09-2026,200,200,200,200,100,0.0,0.0",
               "X,09-09-2026,210,210,210,210,100,0.0,2.0",
               "X,10-09-2026,220,220,220,220,100,0.0,0.0",
               "X,11-09-2026,110,110,110,110,300,0.0,2.0"]
    open(p2, "w").write("\n".join([hdr] + shifted) + "\n")
    assert len(adjust(p2)) == 1, "one event, two flags -> one adjustment"
    assert [float(l.split(",")[5]) for l in
            open(p2).read().strip().splitlines()[1:]] == [100.0, 105.0, 110.0, 110.0]

    # Already adjusted: the flag is there, the level never shifts.
    p3 = os.path.join(d, "c.csv")
    open(p3, "w").write("\n".join([hdr] + [
        f"X,0{n}-09-2026,200,200,200,200,100,0.0,{'2.0' if n == 5 else '0.0'}"
        for n in range(1, 10)]) + "\n")
    assert adjust(p3) == [], "no level shift -> nothing to adjust"

    # A single halved bar next to the flag is a bad print, not a corporate
    # action -- LT 27-09-2006. Adjacent closes match 2.0 exactly; medians do not.
    p4 = os.path.join(d, "d.csv")
    open(p4, "w").write("\n".join([hdr] + [
        f"X,0{n}-09-2026,200,200,200,{100 if n == 4 else 200},100,0.0,"
        f"{'2.0' if n == 5 else '0.0'}" for n in range(1, 10)]) + "\n")
    assert adjust(p4) == [], "one-bar spike must not count as a split"
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.exit(main())
