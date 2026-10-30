"""
build_october_tradelist.py
--------------------------
Turn each engine's October target book into a trade list against the positions
actually held, and book out anything the index rebalance removed.

Why this exists. Every engine derives "Prev Qty" from its OWN recomputed
history, not from the book that was published and traded. Feeding the
post-rebalance October universe through 80 months rewrites that history -- the
recomputed September book even holds BSE, SEDEMAC, SENORES and MINDSPACE, which
only joined the index on 30-09-2026 -- so the deltas were being measured against
a September that never existed:

    BHARTIARTL  engine says prev=440    actually held 551
    LENSKART    engine says prev=929    actually held 1216
    VEDL        engine says prev=0      actually held 3056

Worse, a held name the rebalance dropped simply vanishes from the target book.
CORONA is gone from TOTAL_STOCKS_October, so nothing told anyone to sell it;
across the five books 26 positions would have been left stranded.

So: target quantities and weights come from the October run, which is the part
that is sound; every delta is measured against the REAL prior holding; and every
held name missing from the target becomes an explicit EXIT row priced at the
latest close.

    python build_october_tradelist.py
    python build_october_tradelist.py --out x.xlsx
"""
import argparse
import json
import os
import re

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from live_prices import price_symbols

MAIN = os.path.dirname(os.path.abspath(__file__))
# The SPLICED books, not the raw October run. build_october_books.py /
# build_october_hq.py / build_october_ml.py already carry the published history,
# the real September Prev Qty and the exit rows, so reading them keeps one source
# of truth instead of re-deriving the same deltas from a run whose own history
# and September book had drifted.
OCT = os.path.join(MAIN, "scratch", "spliced")
HELD_JSON = os.environ.get(
    "HELD_JSON", os.path.join(MAIN, "scratch", "published_september.json"))

PRICE_FOLDERS = ["nifty_50_october", "nifty_500_october", "TOTAL_STOCKS_October",
                 "hq_quarterly_universe", "High_Quality_October",
                 "TOTAL_STOCKS", "nifty500_host",
                 r"d:\PC2546\portfolio\NIFTY500"]
BULLION = {"GOLDBEES": "NSE_GOLDBEES, 1D.csv",
           "SILVERBEES": "NSE_SILVERBEES, 1D.csv"}

HDR_FILL = PatternFill("solid", fgColor="1F3864")
EXIT_FILL = PatternFill("solid", fgColor="FCE4E4")
WHITE = Font(color="FFFFFF", bold=True)


def target_from_port(path):
    """Hedge books: the last Port_ sheet carries the target book."""
    xl = pd.ExcelFile(path)
    sheets = sorted(s for s in xl.sheet_names if re.fullmatch(r"Port_\d{4}-\d{2}", s))
    sh = sheets[-1]
    d = xl.parse(sh, header=None)
    h = next(i for i in range(len(d)) if str(d.iloc[i, 0]).strip() == "Stock")
    out = {}
    for _, r in d.iloc[h + 1:].iterrows():
        s = str(r.iloc[0]).replace("_1d_max", "").strip()
        if s in ("nan", "", "None"):
            continue
        qty, w = float(r.iloc[9] or 0), float(r.iloc[1] or 0)
        if qty > 0:
            out[s] = {"qty": qty, "w": w, "px": 0.0}
    return sh, out


def target_from_current(path):
    """HQ / ML: the Current workbook's Selection_ sheet."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    out = {}
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not r or not r[0]:
            continue
        s = str(r[0]).replace("_1d_max", "").strip()
        qty = float(r[3] or 0)
        if qty > 0:
            out[s] = {"qty": qty, "w": float(r[5] or 0), "px": float(r[6] or 0)}
    return wb.sheetnames[0], out


BOOKS = [
    ("Nifty 50", "nifty50",
     os.path.join(OCT, "Hedge_nifty50.xlsx"), target_from_port),
    ("Nifty 500", "nifty500",
     os.path.join(OCT, "Hedge_nifty500.xlsx"), target_from_port),
    ("All Indices", "total759",
     os.path.join(OCT, "Hedge_Pro_Summary_759.xlsx"), target_from_port),
    ("High Quality", "high_quality",
     os.path.join(OCT, "SOM_HQ_Quarterly_v2_Current.xlsx"), target_from_current),
    ("ML Forecast", "ml_forecast",
     os.path.join(OCT, "Current_Portfolio_ML_Forecast_NIFTY500.xlsx"),
     target_from_current),
]

COLS = ["Symbol", "Action", "Target Qty", "Held Qty", "Change",
        "Target Wt %", "Price", "Value", "Note"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        MAIN, "SQE October_2026 Trade List.xlsx"))
    args = ap.parse_args()

    held = json.load(open(HELD_JSON, encoding="utf-8"))
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Summary"
    summary = []

    for label, key, path, loader in BOOKS:
        if not os.path.exists(path):
            print(f"[skip] {label}: {path} not found")
            continue
        sheet, tgt = loader(path)
        prev = {k: v["qty"] for k, v in held[key].items()
                if v.get("qty") is not None}

        syms = sorted(set(tgt) | set(prev))
        quotes = price_symbols(syms, PRICE_FOLDERS, aliases=BULLION)

        rows, unpriced = [], []
        for s in syms:
            t = tgt.get(s)
            p = int(prev.get(s, 0))
            px = quotes.get(s, {}).get("ltp") or (t or {}).get("px") or 0.0
            if not px:
                unpriced.append(s)
            if t:
                q = int(round(t["qty"]))
                delta = q - p
                act = ("HOLD" if delta == 0
                       else (f"BUY {delta}" if delta > 0 else f"SELL {abs(delta)}"))
                rows.append([s, act, q, p, delta, round(t["w"] * 100, 2),
                             px, round(q * px), ""])
            elif p > 0:
                # Held but absent from the current list: the rebalance removed it.
                # It must be sold, not dropped -- that is the whole point here.
                rows.append([s, f"EXIT SELL {p}", 0, p, -p, 0.0, px, 0,
                             "not in current universe - book it out"])
            # p == 0 and not in target: a zero-weight leftover row in the prior
            # book, not a real position. SOLARINDS sat in September's Nifty 500
            # that way; emitting "EXIT SELL 0" for it is a no-op instruction.
        rows.sort(key=lambda r: (-r[5], r[0]))

        ws = wb.create_sheet(label[:31])
        ws["A1"] = f"{label} - October 2026 trade list"
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"] = (f"Target from {os.path.basename(path)} ({sheet}). Held Qty is the "
                    f"published September book, not the engine's recomputed one. "
                    f"EXIT rows are positions the rebalance removed - sell them.")
        ws["A2"].font = Font(size=9, color="595959")
        for j, c in enumerate(COLS, 1):
            cell = ws.cell(4, j, c)
            cell.fill, cell.font = HDR_FILL, WHITE
            cell.alignment = Alignment(horizontal="center")
        for i, r in enumerate(rows, 5):
            for j, v in enumerate(r, 1):
                cell = ws.cell(i, j, v)
                if str(r[1]).startswith("EXIT"):
                    cell.fill = EXIT_FILL
            ws.cell(i, 6).number_format = "0.00"
            ws.cell(i, 7).number_format = "#,##0.00"
            ws.cell(i, 8).number_format = "#,##0"
        for j, w in enumerate([14, 16, 11, 10, 9, 12, 11, 13, 40], 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "A5"

        exits = [r for r in rows if str(r[1]).startswith("EXIT")]
        buys = [r for r in rows if str(r[1]).startswith("BUY")]
        sells = [r for r in rows if str(r[1]).startswith("SELL")]
        holds = [r for r in rows if r[1] == "HOLD"]
        val = sum(r[7] for r in rows if not str(r[1]).startswith("EXIT"))
        exval = sum(r[3] * r[6] for r in exits)
        carried = len([r for r in rows if r[2] and r[3]])
        newb = len([r for r in rows if r[2] and not r[3]])
        summary.append((label, sheet, len(tgt), len(prev), len(buys), len(sells),
                        len(holds), exits, unpriced, round(val), carried, newb,
                        round(exval)))

    # ---- Summary sheet, written last so it can quote the per-book totals ----
    ws_sum["A1"] = "SQE - October 2026 portfolios"
    ws_sum["A1"].font = Font(bold=True, size=14)
    ws_sum["A2"] = ("One sheet per book. Held Qty is the published September book, "
                    "not the engine's recomputed one. EXIT rows are positions the "
                    "30-09-2026 index rebalance removed - they must be sold.")
    ws_sum["A2"].font = Font(size=9, color="595959")
    scols = ["Book", "Source sheet", "Holdings", "Book value",
             "Carried", "New buys", "Exits", "Exit value"]
    for j, c in enumerate(scols, 1):
        cell = ws_sum.cell(4, j, c)
        cell.fill, cell.font = HDR_FILL, WHITE
        cell.alignment = Alignment(horizontal="center")
    for i, (lbl, sh, nt, nh, nb, ns, nhold, ex, unp, val, carried, newb,
            exval) in enumerate(summary, 5):
        for j, v in enumerate([lbl, sh, nt, val, carried, newb, len(ex), exval], 1):
            ws_sum.cell(i, j, v).border = None
        ws_sum.cell(i, 4).number_format = '#,##0'
        ws_sum.cell(i, 8).number_format = '#,##0'
    for j, w in enumerate([16, 20, 10, 15, 10, 11, 8, 15], 1):
        ws_sum.column_dimensions[get_column_letter(j)].width = w
    ws_sum.freeze_panes = "A5"

    wb.save(args.out)
    print(f"{'book':<14}{'sheet':<19}{'tgt':>5}{'held':>6}{'buy':>5}{'sell':>6}"
          f"{'hold':>6}{'EXIT':>6}")
    for r in summary:
        lbl, sh, nt, nh, nb, ns, nhold, ex = r[:8]
        print(f"{lbl:<14}{sh:<19}{nt:>5}{nh:>6}{nb:>5}{ns:>6}{nhold:>6}{len(ex):>6}")
    print()
    for r in summary:
        lbl, ex, unp = r[0], r[7], r[8]
        if ex:
            print(f"  {lbl}: book out {', '.join(r[0] + ' x' + str(r[3]) for r in ex)}")
        if unp:
            print(f"  {lbl}: WARNING no price for {', '.join(unp)}")
    print(f"\nwrote -> {args.out}")


if __name__ == "__main__":
    main()
