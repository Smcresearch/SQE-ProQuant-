"""
Build per-month Base SIM holdings (MONTHLY_HOLDINGS) for the SQE All-Indices
site from the Port_YYYY-MM sheets in Hedge_Pro_Summary_759.xlsx.

Output: d:/SQE-host/holdings.js  ->  const MONTHLY_HOLDINGS = { "YYYY-MM": [...] }
Each holding: { s: clean symbol, w: SIM weight %, p: price, r: month return %,
               st: status, a: action, b: beta, e: erb }

Price: each sheet's Qty was sized as weight * CAPITAL / price, so
       price = weight * CAPITAL / Qty (CAPITAL is a stable ~1 crore notional).
Return: the formation price recovers that month's market price, so a stock's
        return during month M ~= price[M+1] / price[M] - 1 (validated at ~1-2pp
        mean error vs real historical prices). Null for a holding's last month.
Sectors are resolved on the front-end via DASHBOARD_DATA.sector_map.
"""
import json
import os
import re
import math
import pandas as pd

# Override per site via env: e.g. HOLDINGS_SRC=Hedge_nifty500.xlsx
# HOLDINGS_OUT=d:/SQE-ProQuant-host/holdings.js
SRC = os.environ.get('HOLDINGS_SRC', 'Hedge_Pro_Summary_759.xlsx')
OUT = os.environ.get('HOLDINGS_OUT', r'd:/SQE-host/holdings.js')
CAPITAL = 10_000_000


def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def main():
    xl = pd.ExcelFile(SRC)
    port_sheets = sorted(s for s in xl.sheet_names if re.fullmatch(r'Port_\d{4}-\d{2}', s))

    months_data = {}   # month -> list of holding dicts (with 'full' symbol key)
    price = {}         # month -> { full_symbol: price }

    for sh in port_sheets:
        month = sh.replace('Port_', '')
        df = pd.read_excel(xl, sheet_name=sh, header=1)
        if 'Stock' not in df.columns or 'SIM Weight' not in df.columns:
            continue

        rows, pm = [], {}
        for _, r in df.iterrows():
            stock = str(r.get('Stock', '')).strip()
            if not stock or stock.lower() == 'nan':
                continue
            w = num(r.get('SIM Weight'))
            if not w or w <= 0:          # Base SIM portfolio only
                continue
            q = num(r.get('Qty'))
            p = (w * CAPITAL / q) if (q and q > 0) else None
            if p is not None:
                pm[stock] = p
            rows.append({
                'full': stock,
                's': stock.split('_')[0],
                'w': round(w * 100, 2),
                'p': round(p, 2) if p is not None else None,
                'st': str(r.get('Status', '')).strip() or '—',
                'a': str(r.get('Action', '')).strip() or '—',
                'b': round(num(r.get('Beta')) or 0, 3),
                'e': round(num(r.get('ERB')) or 0, 3),
            })
        months_data[month] = rows
        price[month] = pm

    # Per-stock month return from the next month's formation price.
    months = sorted(months_data)
    for i, m in enumerate(months):
        nxt = months[i + 1] if i + 1 < len(months) else None
        for row in months_data[m]:
            r = None
            if nxt and row['p']:
                p1 = price[nxt].get(row['full'])
                if p1:
                    r = round((p1 / row['p'] - 1) * 100, 2)
            row['r'] = r
            del row['full']
        months_data[m].sort(key=lambda x: x['w'], reverse=True)

    payload = json.dumps(months_data, separators=(',', ':'), ensure_ascii=False)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('/* Per-month Base SIM holdings for the heatmap modal. Auto-generated. */\n')
        f.write('const MONTHLY_HOLDINGS = ' + payload + ';\n')

    total = sum(len(v) for v in months_data.values())
    print(f'[holdings] {len(months_data)} months, {total} holding rows -> {OUT}')
    s = next(iter(months_data))
    print(f'[holdings] sample {s}: {len(months_data[s])} stocks, first = {months_data[s][0] if months_data[s] else None}')


if __name__ == '__main__':
    main()
