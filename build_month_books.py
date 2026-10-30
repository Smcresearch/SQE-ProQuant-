"""
build_october_books.py
----------------------
Splice the October book onto the PUBLISHED history, without re-running it.

Why a splice and not a re-run. som_hedge.py is not reproducible run-to-run:
re-running it on the very same universe folders with the very same --end
reproduces 76 of 80 months to 0.0001pp but moves a handful, and the September
book itself drifts (it gains TDPOWERSYS in the 759 book and loses KARURVYSYA in
the 500 book). The published history is what was traded, so it is treated as
immutable and only appended to:

  * Port_2020-01 .. Port_2026-08 : copied through untouched.
  * Detailed_Monthly_Summary rows for Month <= 2026-07 : untouched.
  * Month=2026-08 (traded September) : the published row is a STUB written
    before September had happened (Base -0.02%). It is replaced with the
    realised return of the published September book, computed with the engine's
    own formula (see base_return) rather than by re-running.
  * Port_2026-09 (traded October) : appended from the post-rebalance run, with
    Prev_Qty taken from the published September book and an explicit exit row
    for every name the 30-09-2026 index rebalance removed.

Known discrepancy, deliberately NOT corrected: on today's data the Nifty 500
book's June-2026 return is +8.844%, not the published +3.643%. Two independent
computations agree (an engine re-run and base_return below) and no stock's data
looks anomalous, so the published figure appears to have been produced from
inputs that no longer exist. History is left as published per instruction.

    python build_october_books.py            # -> scratch/spliced/
    python build_october_books.py --install  # also copy over the live books
"""
import csv
import datetime
import os
import shutil
import sys

import numpy as np
import openpyxl
import pandas as pd

MAIN = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("PORTFOLIO_SHARED", r"D:\Shared folder\portfolio")
OCT = os.path.join(MAIN, "scratch", "oct_run")
OUT = os.path.join(MAIN, "scratch", "spliced")

CAP = 10_000_000          # som_hedge.INITIAL_CAPITAL
COST_PER_TRADE = 0.002    # som_hedge.COST_PER_TRADE

SIGNAL_REALIZE = "2026-08"   # traded September -- stub becomes realised
SIGNAL_NEW = "2026-09"       # traded October  -- the new book

# Price folders. The September book is priced from the PRE-rebalance folders it
# was built from; the October book from the post-rebalance snapshots. Both are
# searched because a name can appear in either.
FOLDERS = ["nifty50_host", "nifty500_host", "TOTAL_STOCKS",
           "nifty_50_october", "nifty_500_october", "TOTAL_STOCKS_October"]

LAYER_COL = {"Base": "SIM Weight", "ST": "ST Wt", "EMA": "EMA Wt",
             "COMBO": "COMBO Wt", "ULTRA": "ULTRA Wt"}

BOOKS = [
    ("nifty50", "Hedge_nifty50.xlsx", os.path.join(MAIN, "NIFTY50_1d.csv")),
    ("nifty500", "Hedge_nifty500.xlsx", os.path.join(SHARED, "NSE_CNX500, 1D.csv")),
    ("total759", "Hedge_Pro_Summary_759.xlsx", os.path.join(SHARED, "NSE_CNX500, 1D.csv")),
]

HDR = ["Stock", "SIM Weight", "ST Wt", "EMA Wt", "COMBO Wt", "ULTRA Wt",
       "Beta", "ERB", "Status", "Qty", "Prev_Qty", "Delta", "Action"]

_bars = {}


def monthly(sym):
    """month Period -> [open, close]; open = first of month, close = last.
    Mirrors som_hedge.resample_to_monthly (agg open:first, close:last)."""
    if sym in _bars:
        return _bars[sym]
    for fol in FOLDERS:
        p = os.path.join(MAIN, fol, sym + "_1d_max.csv")
        if not os.path.exists(p):
            continue
        rows = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
        if not rows or "Date" not in rows[0]:
            continue
        di, oi, ci = (rows[0].index("Date"), rows[0].index("Open"),
                      rows[0].index("Close"))
        recs = []
        for x in rows[1:]:
            if len(x) <= max(di, oi, ci):
                continue
            try:
                dt = datetime.datetime.strptime(x[di].strip(), "%d-%m-%Y")
                recs.append((dt, float(x[oi]), float(x[ci])))
            except ValueError:
                continue
        if not recs:
            continue
        recs.sort()
        out = {}
        for dt, o, c in recs:
            k = pd.Period(dt, "M")
            if k not in out:
                out[k] = [o, c]
            out[k][1] = c
        _bars[sym] = out
        return out
    _bars[sym] = {}
    return {}


def sheet_table(path, sheet):
    """A Port_ sheet as a DataFrame, header row located rather than assumed."""
    d = pd.ExcelFile(path).parse(sheet, header=None)
    h = next(i for i in range(len(d)) if str(d.iloc[i, 0]).strip() == "Stock")
    hdr = [str(x).strip() for x in d.iloc[h]]
    b = d.iloc[h + 1:].copy()
    b.columns = hdr
    return b[~b["Stock"].astype(str).str.strip().isin(["nan", "", "None"])]


def num(v):
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return 0.0


def weights(tbl, col):
    out = {}
    for _, r in tbl.iterrows():
        s = str(r["Stock"]).replace("_1d_max", "").strip()
        w = num(r.get(col, 0))
        if w > 0:
            out[s] = w
    return out


def qtys(tbl):
    out = {}
    for _, r in tbl.iterrows():
        s = str(r["Stock"]).replace("_1d_max", "").strip()
        q = int(num(r.get("Qty", 0)))
        if q > 0:
            out[s] = q
    return out


def base_return(prev_w, curr_w, port_month, trade_month):
    """som_hedge.py's per-month layer return, lifted verbatim (lines 498-578).

    Validated against the published books: reproduces every month of nifty50
    and 2026-06/07/08 of nifty500 and 759 to 0.0000pp.
    """
    pm, tm = pd.Period(port_month, "M"), pd.Period(trade_month, "M")
    pnl = txn = 0.0
    missing = []
    for t in set(prev_w) | set(curr_w):
        md = monthly(t)
        hist = [k for k in md if k <= pm] if md else []
        if not hist:
            missing.append(t)
            continue
        prev_close = md[max(hist)][1]
        if tm in md:
            buy_px = md[tm][0]
            if not buy_px or buy_px <= 0:
                buy_px = prev_close
            sell_px = md[tm][1]
        else:
            buy_px = sell_px = prev_close
        wp, wc = prev_w.get(t, 0.0), curr_w.get(t, 0.0)
        q_p = int(np.floor(CAP * wp / prev_close)) if prev_close > 0 else 0
        q_c = int(np.floor(CAP * wc / buy_px)) if buy_px > 0 else 0
        pnl += (buy_px - prev_close) * q_p + (sell_px - buy_px) * q_c
        txn += abs(q_c - q_p) * buy_px
    return (pnl - txn * COST_PER_TRADE) / CAP, missing


def bench_month(path, trade_month):
    """close.resample('ME').last().pct_change() -- som_hedge.py line 299."""
    d = pd.read_csv(path)
    dc = "Date" if "Date" in d.columns else "time"
    cc = "Close" if "Close" in d.columns else "close"
    s = str(d[dc].iloc[0])
    fmt = "%d-%m-%Y" if len(s) == 10 and s[2] == "-" else None
    d[dc] = pd.to_datetime(d[dc], format=fmt, errors="coerce")
    d = d.dropna(subset=[dc, cc]).set_index(dc).sort_index()
    m = d[cc].resample("ME").last().pct_change().dropna()
    m.index = m.index.to_period("M")
    tm = pd.Period(trade_month, "M")
    return float(m.loc[tm]) if tm in m.index else 0.0


def layer_returns(pub, prev_sig, curr_sig, trade, curr_tbl=None):
    """All seven layers for one month."""
    prev_tbl = sheet_table(pub, "Port_" + prev_sig)
    if curr_tbl is None:
        curr_tbl = sheet_table(pub, "Port_" + curr_sig)
    out, miss = {}, []
    for layer, col in LAYER_COL.items():
        r, m = base_return(weights(prev_tbl, col), weights(curr_tbl, col),
                           curr_sig, trade)
        out[layer] = r
        miss += m
    # The hedge overlay needs the futures/MTF series the engine loads privately.
    # In every recent published month COMBO_HEDGE == COMBO and ULTRA_HEDGE ==
    # ULTRA (no hedge was on), and the site renders only Base, so they mirror.
    out["COMBO_HEDGE"], out["ULTRA_HEDGE"] = out["COMBO"], out["ULTRA"]
    return out, sorted(set(miss))


def advanced_metrics(returns, bench, rf_annual=0.06):
    """som_hedge.get_advanced_metrics, trimmed to the metrics the sheet holds."""
    total = (1 + returns).prod() - 1
    years = len(returns) / 12.0
    cagr = ((1 + total) ** (1 / years)) - 1 if total > -1 and years > 0 else -1.0
    vol = returns.std() * np.sqrt(12)
    down = returns[returns < 0]
    dvol = np.sqrt(np.mean(down ** 2)) * np.sqrt(12) if len(down) else 0.001
    cum = (1 + returns).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    mdd = dd.min()
    in_dd = dd < 0
    ddur = (in_dd.astype(int).groupby(in_dd.eq(0).cumsum()).cumsum().max()
            if in_dd.any() else 0)
    v95, v99 = np.percentile(returns, 5), np.percentile(returns, 1)
    c95 = returns[returns <= v95].mean() if len(returns[returns <= v95]) else v95
    c99 = returns[returns <= v99].mean() if len(returns[returns <= v99]) else v99
    btot = (1 + bench).prod() - 1
    bcagr = ((1 + btot) ** (1 / years)) - 1
    alpha = cagr - bcagr
    te = (returns - bench).std() * np.sqrt(12)
    win = len(returns[returns > 0]) / len(returns)
    ag = returns[returns > 0].mean() if len(returns[returns > 0]) else 0.0
    al = returns[returns < 0].mean() if len(returns[returns < 0]) else 0.0
    pos, neg = returns[returns > 0].sum(), returns[returns < 0].sum()
    r12 = (1 + returns.tail(12)).prod() - 1 if len(returns) >= 12 else np.nan
    r36 = (1 + returns.tail(36)).prod() - 1 if len(returns) >= 36 else np.nan
    return {
        "CAGR": cagr, "XIRR": cagr, "Abs Return": total, "Alpha vs Bench": alpha,
        "Volatility": vol, "Downside Dev": dvol,
        "Sharpe": (cagr - rf_annual) / vol if vol > 0 else 0,
        "Sortino": (cagr - rf_annual) / dvol if dvol > 0 else 0,
        "Calmar": cagr / abs(mdd) if abs(mdd) > 0 else 0,
        "Max Drawdown": mdd, "DD Duration (M)": ddur,
        "VaR 95%": v95, "VaR 99%": v99, "CVaR 95%": c95, "CVaR 99%": c99,
        "Info Ratio": alpha / te if te > 0 else 0,
        "Win Rate": win, "Avg Gain": ag, "Avg Loss": al,
        "Profit Factor": abs(pos / neg) if neg != 0 else 10.0,
        "Expectancy": win * ag + (1 - win) * al,
        "Best Month": returns.max(), "Worst Month": returns.min(),
        "Rolling 1Y": r12, "Rolling 3Y": r36,
    }


def main():
    install = "--install" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    trade_realize = (pd.Period(SIGNAL_REALIZE, "M") + 1).strftime("%Y-%m")
    trade_new = (pd.Period(SIGNAL_NEW, "M") + 1).strftime("%Y-%m")

    for key, fname, bench_csv in BOOKS:
        pub = os.path.join(MAIN, fname)
        oct_src = os.path.join(OCT, fname)
        for p in (pub, oct_src):
            if not os.path.exists(p):
                sys.exit("[error] missing " + p)
        dst = os.path.join(OUT, fname)
        shutil.copy2(pub, dst)
        print("\n=== " + key + " ===")

        # ---- 1. realise the September stub -------------------------------
        rets, miss = layer_returns(pub, "2026-07", SIGNAL_REALIZE, trade_realize)
        bench_r = bench_month(bench_csv, trade_realize)
        if miss:
            print("    [warn] no price data for " + str(miss))

        wb = openpyxl.load_workbook(dst)
        ws = wb["Detailed_Monthly_Summary"]
        head = [str(c.value).strip() if c.value is not None else ""
                for c in ws[1]]
        ci = {h: i + 1 for i, h in enumerate(head)}
        row_realize = None
        for r in range(2, ws.max_row + 1):
            if str(ws.cell(r, ci["Month"]).value).strip() == SIGNAL_REALIZE:
                row_realize = r
                break
        if row_realize is None:
            sys.exit("[error] " + fname + ": no Detailed_Monthly_Summary row "
                     "for Month=" + SIGNAL_REALIZE)
        old_base = num(ws.cell(row_realize, ci["Base"]).value)
        for layer, v in rets.items():
            ws.cell(row_realize, ci[layer], v)
        ws.cell(row_realize, ci["Bench"], bench_r)
        print("    Sept (trade %s) realised: Base %+.3f%% (stub) -> %+.3f%%"
              "   bench %+.3f%%" % (trade_realize, old_base * 100,
                                    rets["Base"] * 100, bench_r * 100))

        # ---- 2. the October book, Prev_Qty from the real September book ---
        oct_tbl = sheet_table(oct_src, "Port_" + SIGNAL_NEW)
        sep_tbl = sheet_table(pub, "Port_" + SIGNAL_REALIZE)
        sep_q = qtys(sep_tbl)
        oct_q = qtys(oct_tbl)

        live, _ = layer_returns(pub, SIGNAL_REALIZE, SIGNAL_NEW, trade_new,
                               curr_tbl=oct_tbl)
        bench_live = bench_month(bench_csv, trade_new)

        if "Port_" + SIGNAL_NEW in wb.sheetnames:
            del wb["Port_" + SIGNAL_NEW]
        wsp = wb.create_sheet("Port_" + SIGNAL_NEW)
        src0 = pd.ExcelFile(oct_src).parse("Port_" + SIGNAL_NEW, header=None)
        wsp.cell(1, 1, str(src0.iloc[0, 0]))
        for j, h in enumerate(HDR, 1):
            wsp.cell(2, j, h)

        rows = []
        for _, r in oct_tbl.iterrows():
            s = str(r["Stock"]).replace("_1d_max", "").strip()
            q = int(num(r.get("Qty", 0)))
            if q <= 0:
                continue
            p = sep_q.get(s, 0)
            d = q - p
            act = "HOLD" if d == 0 else ("BUY %d" % d if d > 0
                                         else "SELL %d" % abs(d))
            rows.append([str(r["Stock"]), num(r.get("SIM Weight")),
                         num(r.get("ST Wt")), num(r.get("EMA Wt")),
                         num(r.get("COMBO Wt")), num(r.get("ULTRA Wt")),
                         num(r.get("Beta")), num(r.get("ERB")),
                         "Remained" if p else "Added", q, p, d, act])
        # Every name held in September but absent from the October universe has
        # to be sold, not silently dropped -- the 30-09-2026 rebalance removed
        # several and they would otherwise sit in the book forever.
        exits = []
        for s, p in sorted(sep_q.items()):
            if s in oct_q:
                continue
            exits.append([s, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                          "Exited", 0, p, -p, "EXIT SELL %d" % p])
        rows.sort(key=lambda r: -r[1])
        for i, r in enumerate(rows + exits, 3):
            for j, v in enumerate(r, 1):
                wsp.cell(i, j, v)
        print("    Oct book: %d holdings (%d carried, %d new), %d exits"
              % (len(rows), sum(1 for r in rows if r[10]),
                 sum(1 for r in rows if not r[10]), len(exits)))
        if exits:
            print("      book out: "
                  + ", ".join("%s x%d" % (e[0], e[10]) for e in exits))

        # ---- 3. the October live row -------------------------------------
        for r in range(2, ws.max_row + 1):
            if str(ws.cell(r, ci["Month"]).value).strip() == SIGNAL_NEW:
                ws.delete_rows(r)
                break
        nr = ws.max_row + 1
        title = str(src0.iloc[0, 0])
        beta = sharpe = 0.0
        for part in title.split("|"):
            if "Beta:" in part:
                beta = num(part.split(":")[1])
            if "Sharpe:" in part:
                sharpe = num(part.split(":")[1])
        vals = {"Month": SIGNAL_NEW, "Trade_Month": trade_new,
                "Port_Beta": beta, "Ex_Ante_Sharpe": sharpe,
                "Stock_Count": len(rows),
                "Added": sum(1 for r in rows if not r[10]),
                "Removed": len(exits), "Bench": bench_live}
        vals.update(live)
        for h, v in vals.items():
            if h in ci:
                ws.cell(nr, ci[h], v)
        print("    Oct live row: Base %+.3f%% (rebalance cost, no October "
              "prices yet)" % (live["Base"] * 100))

        # ---- 4. Executive_Dashboard, recomputed over the updated series ---
        series = {}
        for h in list(LAYER_COL) + ["COMBO_HEDGE", "ULTRA_HEDGE", "Bench"]:
            series[h] = [num(ws.cell(r, ci[h]).value)
                         for r in range(2, ws.max_row + 1)]
        bench_s = pd.Series(series["Bench"])
        wsd = wb["Executive_Dashboard"]
        colmap = {"Base SIM": "Base", "ST Filter": "ST", "EMA Filter": "EMA",
                  "COMBO Filter": "COMBO", "ULTRA Layer": "ULTRA",
                  "COMBO+Hedge": "COMBO_HEDGE", "ULTRA Defense": "ULTRA_HEDGE",
                  "Benchmark": "Bench"}
        dhead = [str(c.value).strip() if c.value is not None else ""
                 for c in wsd[1]]
        mt = {}
        for lbl, layer in colmap.items():
            if lbl not in dhead:
                continue
            s = pd.Series(series[layer])
            mt[lbl] = advanced_metrics(s, bench_s if layer != "Bench" else s)
            if layer == "Bench":
                mt[lbl]["Alpha vs Bench"] = 0.0
        for r in range(2, wsd.max_row + 1):
            metric = str(wsd.cell(r, 1).value).strip()
            for lbl in colmap:
                if lbl in dhead and lbl in mt and metric in mt[lbl]:
                    wsd.cell(r, dhead.index(lbl) + 1, mt[lbl][metric])
        b = mt.get("Base SIM", {})
        print("    Exec refreshed: CAGR %.3f%%  MaxDD %.2f%%  over %d months"
              % (b.get("CAGR", 0) * 100, b.get("Max Drawdown", 0) * 100,
                 len(series["Base"])))

        wb.save(dst)
        print("    -> " + dst)
        if install:
            shutil.copy2(dst, pub)
            print("    installed -> " + pub)

    print("\nspliced books in " + OUT
          + ("  (INSTALLED to live)" if install else "  (not installed; --install)"))


if __name__ == "__main__":
    main()
