"""
extract_ml.py
-------------
Rebuild ml_data.js (the ML Forecast tab) from the ML pipeline's own workbooks.

The original extract_ml.py was deleted along with update_sqe.py and extract_hq.py.
This is a reconstruction, verified against the ml_data.js that was live: the
workbook's "Port Return %" for trade month 2020-01 is -0.104838, which is the
first Base value the published file carried, to every decimal.

Two conventions this has to get right, both of which are easy to invert:

  * Rows are keyed by TRADE month, not Portfolio (signal) month. The workbook
    carries both; the dashboard's monthly_detail[].Month is the trade month.
    Keying by signal month shifts the whole series one month and makes the
    history look like a different strategy (mean error 12pp instead of 0.6pp).
  * The final row is a placeholder: the basket is formed but its month has not
    been realized, so Port Return % is 0. app.js renders the LAST
    monthly_detail row as a "live, not yet traded" marker, so exactly one such
    row is kept and it is excluded from every statistic.

Preserved untouched from the existing ml_data.js: stock_correlation,
exec_history, live_performance, and MONTHLY_HOLDINGS.

    python extract_ml.py
"""
import json
import os
import re

import numpy as np
import pandas as pd

ML_DIR = os.environ.get("ML_PIPELINE_DIR", r"d:\PC2546\portfolio")
SUMMARY_XLSX = os.path.join(ML_DIR, "Sharpe_ML_Forecast_NIFTY500_Summary.xlsx")
CURRENT_XLSX = os.path.join(ML_DIR, "Current_Portfolio_ML_Forecast_NIFTY500.xlsx")
ML_DATA_JS = r"d:\Host_portfolio\ml_data.js"
DATA_JS = r"d:\Host_portfolio\data.js"          # only for its sector_map

RF_ANNUAL = 0.06
_norm = lambda x: re.sub(r"\s+", " ", str(x)).strip()


def dd_recovery_months(equity):
    peak, trough_i, max_dd = equity[0], None, 0.0
    for i, v in enumerate(equity):
        peak = max(peak, v)
        dd = v / peak - 1
        if dd < max_dd:
            max_dd, trough_i = dd, i
    if trough_i is None:
        return 0, False
    peak_before = max(equity[: trough_i + 1])
    for j in range(trough_i + 1, len(equity)):
        if equity[j] >= peak_before:
            return j - trough_i, False
    return len(equity) - 1 - trough_i, True


def compute_metrics(returns, bench):
    r = pd.Series(returns).dropna()
    b = pd.Series(bench).dropna()
    if len(r) == 0:
        return {}
    n = len(r)
    equity = (1 + r).cumprod()
    cagr = float(equity.iloc[-1]) ** (12 / n) - 1
    vol = r.std() * np.sqrt(12)
    mdd = float((equity / equity.cummax() - 1).min())
    recovery, ongoing = dd_recovery_months(list(equity))
    downside = r[r < 0].std() * np.sqrt(12)
    wins = int((r > 0).sum())
    return {
        "CAGR": round(cagr * 100, 2),
        "Volatility": round(vol * 100, 2),
        "Sharpe": round((cagr - RF_ANNUAL) / vol, 2) if vol > 0 else 0,
        "Sortino": round((cagr - RF_ANNUAL) / downside, 2) if downside > 0 else 0,
        "Calmar": round(cagr / abs(mdd), 2) if mdd else 0,
        "Max_DD": round(mdd * 100, 2),
        "Recovery_Months": recovery,
        "Recovery_Ongoing": ongoing,
        "Win_Rate": round(wins / n * 100, 1),
        "Avg_Gain": round(float(r[r > 0].mean()) * 100, 2) if wins else 0,
        "Avg_Loss": round(float(r[r < 0].mean()) * 100, 2) if (r < 0).sum() else 0,
        "Alpha": round((cagr - float(b.mean()) * 12) * 100, 2) if len(b) else 0,
        "Total_Return": round((float(equity.iloc[-1]) - 1) * 100, 2),
    }


def rolling_return(returns, n):
    if len(returns) < n:
        return None
    return float(np.prod([1 + r for r in returns[-n:]]) - 1)


def dd_duration_months(equity):
    peak_idx = trough_idx = cur_peak = 0
    max_dd = 0.0
    for i, v in enumerate(equity):
        if v > equity[cur_peak]:
            cur_peak = i
        dd = v / equity[cur_peak] - 1
        if dd < max_dd:
            max_dd, peak_idx, trough_idx = dd, cur_peak, i
    return trough_idx - peak_idx


def adv_metrics(returns, bench, ex_sr=0.0, ex_so=0.0):
    r, b = np.array(returns, float), np.array(bench, float)
    n = len(r)
    equity = np.cumprod(1 + r)
    cagr = float(equity[-1] ** (12 / n) - 1) if n else 0.0
    bench_cagr = float(np.prod(1 + b) ** (12 / n) - 1) if n else 0.0
    vol = float(r.std(ddof=1) * np.sqrt(12)) if n > 1 else 0.0
    downside = float(r[r < 0].std(ddof=1) * np.sqrt(12)) if (r < 0).sum() > 1 else 0.0
    dd = equity / np.maximum.accumulate(equity) - 1
    mdd = float(dd.min())
    active = r - b
    gains, losses = r[r > 0], r[r < 0]
    return {
        "CAGR": cagr, "XIRR": cagr, "Abs Return": float(equity[-1] - 1),
        "Alpha vs Bench": cagr - bench_cagr, "Volatility": vol,
        "Downside Dev": downside,
        "Sharpe": (cagr - RF_ANNUAL) / vol if vol else 0.0,
        "Sortino": (cagr - RF_ANNUAL) / downside if downside else 0.0,
        "Calmar": cagr / abs(mdd) if mdd else 0.0, "Max Drawdown": mdd,
        "DD Duration (M)": float(dd_duration_months(equity)),
        "VaR 95%": float(np.percentile(r, 5)), "VaR 99%": float(np.percentile(r, 1)),
        "CVaR 95%": float(r[r <= np.percentile(r, 5)].mean()) if n else 0.0,
        "CVaR 99%": float(r[r <= np.percentile(r, 1)].mean()) if n else 0.0,
        "Info Ratio": float(active.mean() / active.std(ddof=1) * np.sqrt(12))
                      if n > 1 and active.std(ddof=1) else 0.0,
        "Win Rate": float((r > 0).sum() / n) if n else 0.0,
        "Profit Factor": float(gains.sum() / abs(losses.sum())) if losses.sum() else 0.0,
        "Expectancy": float(r.mean()),
        "Avg Gain": float(gains.mean()) if len(gains) else 0.0,
        "Avg Loss": float(losses.mean()) if len(losses) else 0.0,
        "Rolling 1Y": rolling_return(list(r), 12),
        "Rolling 3Y": rolling_return(list(r), 36),
        "Best Month": float(r.max()) if n else 0.0,
        "Worst Month": float(r.min()) if n else 0.0,
        "Avg Ex-Ante Sharpe": ex_sr, "Avg Ex-Ante Sortino": ex_so,
    }


def load_months():
    """Per-month rows from 'Summary FULL', keyed by TRADE month."""
    d = pd.read_excel(SUMMARY_XLSX, "Summary FULL", header=None)
    hdr = next(i for i in range(len(d))
               if any(_norm(x) == "Portfolio Month" for x in d.iloc[i].tolist()))
    cols = [_norm(x) for x in d.iloc[hdr].tolist()]
    t = d.iloc[hdr + 1:].copy()
    t.columns = cols
    t = t[t["Portfolio Month"].astype(str).str.match(r"^\d{4}-\d{2}$")]

    num = lambda c: pd.to_numeric(t[c], errors="coerce") if c in t else pd.Series(0, index=t.index)
    out = []
    for tm, sc, ad, rm, beta, pr, br, sr, so in zip(
            t["Trade Month"].astype(str), num("Stocks"), num("Added Stocks"),
            num("Removed Stocks"), num("Ex-ante Beta"), num("Port Return %"),
            num("Bench Return %"), num("Ex-ante Sharpe"),
            num("Ex-Ante Sortino") if "Ex-Ante Sortino" in t else num("Ex-ante Sharpe") * 0):
        out.append({
            "Month": tm,
            "Stock_Count": float(sc or 0), "Added": float(ad or 0),
            "Removed": float(rm or 0),
            "Port_Beta": round(float(beta or 0), 4),
            "Base": float(pr) if pr == pr else 0.0,
            "Bench": float(br) if br == br else 0.0,
            "Ex_Ante_Sharpe": round(float(sr or 0), 4),
            "Ex_Ante_Sortino": round(float(so or 0), 4),
        })
    return out


# Priced from the settled CSVs the ML run itself read. yfinance was returning a
# placeholder bar for a session that had not happened, and measuring MTD from
# the last bar's month turned "month to date" into the previous month's whole
# return -- ATHERENERG showed +36.29% MTD on day one of a September book.
PRICE_FOLDERS = [r"d:\PC2546\portfolio\NIFTY500", "nifty500_host", "TOTAL_STOCKS"]
BENCH_CSV = r"D:\Shared folder\portfolio\NSE_CNX500, 1D.csv"


def load_current():
    """current_portfolio rows from the ML trade list, priced from local CSVs."""
    from live_prices import price_symbols
    try:
        txt = open(DATA_JS, encoding="utf-8").read()
        i = txt.index("{", txt.index("DASHBOARD_DATA"))
        sectors = json.JSONDecoder().raw_decode(txt[i:])[0].get("sector_map", {})
    except Exception:
        sectors = {}

    d = pd.read_excel(CURRENT_XLSX, header=None)
    hdr = next(i for i in range(len(d)) if _norm(d.iloc[i, 0]) == "Symbol")
    t = d.iloc[hdr + 1:]
    rows = []
    for _, r in t.iterrows():
        sym = str(r.iloc[0]).strip()
        if sym in ("nan", "", "None"):
            continue
        sym = sym.replace("_1d_max", "")
        qty = float(r.iloc[3] or 0)
        if qty <= 0:                      # exits are instructions, not holdings
            continue
        rows.append({"symbol": sym, "clean_symbol": sym,
                     "sector": sectors.get(sym) or "Other",
                     "weight": float(r.iloc[5] or 0),
                     "action": f"{r.iloc[1]} {int(float(r.iloc[2] or 0))}",
                     "status": "Remained", "qty": int(qty),
                     "prev_qty": int(float(r.iloc[4] or 0)),
                     "book_price": float(r.iloc[6] or 0)})

    quotes = price_symbols([h["symbol"] for h in rows], PRICE_FOLDERS)
    for h in rows:
        q = quotes.get(h["symbol"], {})
        if not q.get("ltp"):
            # Never emit 0 -- app.js's qty calculator skips a holding priced 0
            # and silently drops its weight into "Cash Left".
            q = {"ltp": h["book_price"], "prev_close": h["book_price"],
                 "change_pct": 0.0, "mtd_change_pct": 0.0, "date": "N/A"}
            print(f"[ml] WARNING: no local price for {h['symbol']}, "
                  f"using book {h['book_price']}")
        h.update({"ltp": q["ltp"], "prev_close": q["prev_close"],
                  "change_pct": q["change_pct"],
                  "mtd_change_pct": q["mtd_change_pct"],
                  "value": round(h["qty"] * q["ltp"], 2), "date": q["date"]})
        h.pop("book_price")
    return rows


def build_live_performance(holdings):
    """Portfolio vs benchmark, today and MTD, off the same settled closes.
    Zero on day one of a book, which is the honest answer -- the previous code
    carried August's figures forward onto an untraded September basket."""
    from live_prices import aggregate, price_symbols
    pd_, pm = aggregate(holdings)
    b = price_symbols(["BENCH"], [], aliases={"BENCH": BENCH_CSV})["BENCH"]
    if not b["ltp"]:
        print(f"[ml] WARNING: benchmark {BENCH_CSV} unreadable -- reporting 0")
    return {"portfolio_ret": pd_, "benchmark_ret": b["change_pct"],
            "alpha": round(pd_ - b["change_pct"], 2),
            "portfolio_mtd": pm, "benchmark_mtd": b["mtd_change_pct"],
            "alpha_mtd": round(pm - b["mtd_change_pct"], 2),
            "indicator": "up" if pd_ >= 0 else "down"}


def main():
    months = load_months()
    # Exactly one trailing unrealized row is kept as the "live" marker.
    is_live = len(months) > 1 and months[-1]["Base"] == 0.0
    realized = months[:-1] if is_live else months

    base = [m["Base"] for m in realized]
    bench = [m["Bench"] for m in realized]
    ex_sr = round(sum(m["Ex_Ante_Sharpe"] for m in realized) / len(realized), 4)
    ex_so = round(sum(m["Ex_Ante_Sortino"] for m in realized) / len(realized), 4)

    eq_b = eq_n = 1.0
    cb, cn = [], []
    for m in months:
        eq_b *= 1 + m["Base"]; eq_n *= 1 + m["Bench"]
        cb.append(round(eq_b, 4)); cn.append(round(eq_n, 4))

    em_b = adv_metrics(base, bench, ex_sr, ex_so)
    em_n = adv_metrics(bench, bench, 0.0, 0.0)
    lm_n = compute_metrics(bench, bench); lm_n["Alpha"] = 0.0

    old = {}
    if os.path.exists(ML_DATA_JS):
        txt = open(ML_DATA_JS, encoding="utf-8").read()
        m = re.search(r"DASHBOARD_DATA\.ml_forecast\s*=\s*", txt)
        if m:
            old = json.JSONDecoder().raw_decode(txt[txt.index("{", m.end() - 1):])[0]
        hm = re.search(r"MONTHLY_HOLDINGS\.ml_forecast\s*=\s*", txt)
        old_holdings = (json.JSONDecoder().raw_decode(txt[txt.index("{", hm.end() - 1):])[0]
                        if hm else {})
    else:
        old_holdings = {}

    current = load_current()

    payload = {
        "exec_summary": {k: {"Base": em_b[k], "Bench": em_n[k]} for k in em_b},
        "avg_ex_ante_sr": ex_sr,
        "layer_metrics": {"Base": compute_metrics(base, bench), "Bench": lm_n},
        "equity_curves": {"months": [m["Month"] for m in months], "Base": cb, "Bench": cn},
        "churning_data": [{"Month": m["Month"], "Stock_Count": m["Stock_Count"],
                           "Base Add": m["Added"], "Base Rem": m["Removed"]}
                          for m in months],
        "heatmaps": {},
        "monthly_detail": months,
        "current_portfolio": current,
        "exec_history": old.get("exec_history", []),
        "stock_correlation": old.get("stock_correlation", {}),
        "total_months": len(months),
        # Recomputed, not carried forward -- the old value reported
        # portfolio_ret 1.06% / MTD 1.77% on a book that had not traded.
        "live_performance": build_live_performance(current),
    }

    cp = payload["current_portfolio"]
    assert cp, "current_portfolio is empty"
    assert all(h["ltp"] for h in cp), "a holding is priced 0"
    tw = sum(h["weight"] for h in cp)
    assert abs(tw - 1.0) < 0.02, f"weights sum to {tw:.4f}, not ~1.0"

    with open(ML_DATA_JS, "w", encoding="utf-8") as f:
        f.write("/* ML Forecast (NIFTY500) universe + holdings. Auto-generated. */\n")
        f.write("DASHBOARD_DATA.ml_forecast = "
                + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n")
        f.write("if (typeof MONTHLY_HOLDINGS !== 'undefined') MONTHLY_HOLDINGS.ml_forecast = "
                + json.dumps(old_holdings, separators=(",", ":"), ensure_ascii=False) + ";\n")

    lm = payload["layer_metrics"]["Base"]
    print(f"[ml] {len(months)} months ({months[0]['Month']}->{months[-1]['Month']}), "
          f"{len(cp)} current holdings -> {ML_DATA_JS}")
    print(f"[ml] CAGR={lm['CAGR']}% Sharpe={lm['Sharpe']} MaxDD={lm['Max_DD']}% "
          f"| weights {tw:.4f} | all priced")


if __name__ == "__main__":
    main()
