"""
backfill_bhavcopy.py
--------------------
Fill missing sessions into the daily CSVs straight from the exchange bhavcopy.
Yahoo intermittently drops a day for a subset of symbols, and sometimes stalls a
symbol's series entirely (GSPL stops 11-05-2026, JBCHEPHARM 23-07-2026, both
still trading on NSE), so the exchange file is the authority.

NSE first, BSE as fallback for the BSE-only / SME names.

    # one session, whole folder
    python backfill_bhavcopy.py 2026-07-30 --dir "D:/.../High_Quality_August"

    # a date range, only two symbols, ML filenames carry a _1d_max suffix
    python backfill_bhavcopy.py --from 2026-05-12 --to 2026-07-30 \
        --dir "D:/PC2546/portfolio/NIFTY500" --strip-suffix _1d_max \
        --only GSPL,JBCHEPHARM

Bhavcopy prices are unadjusted. For recent bars that matches the auto_adjust
series already in the files, since no later corporate action has been applied.
Dividends / Stock Splits are written as 0.0 - the bhavcopy does not carry them,
so a backfill spanning an ex-date needs a re-adjust.
"""
import csv
import io
import os
import sys
import zipfile
from datetime import datetime, timedelta

import urllib.error
import urllib.request

DEFAULT_DIR = os.environ.get('HQ_AUG_DIR', r'D:/Shared folder/portfolio/High_Quality_August')
CACHE = os.environ.get('BHAV_CACHE', os.path.join(os.path.dirname(os.path.abspath(__file__)), '_bhav'))
DATE_FMT = '%d-%m-%Y'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
TRADED_SERIES = {'EQ', 'BE', 'SM', 'ST', 'SL', 'M', 'MT', 'XT', 'X', 'B', 'A', 'T'}

# CSV stem -> exchange ticker, where they differ (corporate actions / BSE names)
SYMBOL_MAP = {
    'ADORWELD': 'ADOR',
    'SELAN': 'ANTELOPUS',
    'KLBRENG': 'KLBRENG-B',
    'MODERNINS': 'MODINSU',
}


def opt(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


positional = [a for a in sys.argv[1:] if not a.startswith('--')]
DRY_RUN = '--dry-run' in sys.argv
TARGET_DIR = opt('--dir', DEFAULT_DIR)
STRIP_SUFFIX = opt('--strip-suffix', '')
ONLY = {s.strip().upper() for s in opt('--only', '').split(',') if s.strip()}

_from = opt('--from')
_to = opt('--to')
if _from:
    START = datetime.strptime(_from, '%Y-%m-%d')
    END = datetime.strptime(_to or _from, '%Y-%m-%d')
else:
    one = positional[0] if positional else '2026-07-30'
    START = END = datetime.strptime(one, '%Y-%m-%d')


def grab(url, path):
    """Cached download. Returns None when the exchange has no file (holiday)."""
    if os.path.exists(path):
        return path if os.path.getsize(path) > 0 else None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': '*/*', 'Referer': 'https://www.nseindia.com/'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        open(path, 'wb').close()          # mark as absent so we don't refetch
        return None
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def load_bhav(dt):
    """symbol -> OHLCV row for one session. NSE wins over BSE. None if no session."""
    ymd = dt.strftime('%Y%m%d')
    book = {}
    bse = grab(f'https://www.bseindia.com/download/BhavCopy/Equity/'
               f'BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV',
               os.path.join(CACHE, f'bse_{ymd}.csv'))
    if bse:
        with open(bse, encoding='utf-8', errors='replace') as f:
            for r in csv.DictReader(f):
                if r.get('SctySrs') in TRADED_SERIES:
                    book.setdefault(r['TckrSymb'], r)
    nse = grab(f'https://nsearchives.nseindia.com/content/cm/'
               f'BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip',
               os.path.join(CACHE, f'nse_{ymd}.csv.zip'))
    if nse:
        try:
            z = zipfile.ZipFile(nse)
            for r in csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode('utf-8'))):
                if r.get('SctySrs') in TRADED_SERIES:
                    book[r['TckrSymb']] = r
        except zipfile.BadZipFile:
            pass
    return book or None


def read_meta(path):
    """Static (non-OHLCV) column count varies by source folder -- e.g.
    TOTAL_STOCKS/NIFTY500/etc carry Company,Industry,Symbol,Series,ISIN (5)
    before Date, while High_Quality_August carries Symbol,Company,Industry,
    Index (4). Detect it from the header's own 'Date' column instead of
    assuming a fixed count -- assuming 4 unconditionally silently misaligned
    every appended row for 5-static-column files (Date landed in the ISIN
    slot, shifting OHLCV out from under the header)."""
    static, dates = None, set()
    with open(path, encoding='utf-8') as f:
        header = f.readline().rstrip('\n').split(',')
        try:
            date_idx = [h.strip().lower() for h in header].index('date')
        except ValueError:
            date_idx = 4  # no recognizable header -- fall back to the old assumption
        for line in f:
            p = line.rstrip('\n').split(',')
            if len(p) <= date_idx:
                continue
            if static is None:
                static = p[:date_idx]
            dates.add(p[date_idx].strip())
    return static, dates


def main():
    files = sorted(f for f in os.listdir(TARGET_DIR) if f.lower().endswith('.csv'))
    targets = []
    for fn in files:
        stem = fn[:-4]
        sym = stem[:-len(STRIP_SUFFIX)] if STRIP_SUFFIX and stem.endswith(STRIP_SUFFIX) else stem
        if ONLY and sym.upper() not in ONLY:
            continue
        targets.append((fn, sym))

    print(f'[bhav] target : {TARGET_DIR}')
    print(f'[bhav] range  : {START:%Y-%m-%d} .. {END:%Y-%m-%d} | {len(targets)} file(s)')
    if DRY_RUN:
        print('[bhav] DRY RUN - nothing written')

    # state per file, so we append in date order and write once
    state = {}
    for fn, sym in targets:
        static, dates = read_meta(os.path.join(TARGET_DIR, fn))
        state[fn] = {'sym': sym, 'static': static, 'dates': dates, 'new': [],
                     'date_idx': len(static) if static else 4}

    sessions = holidays = 0
    day = START
    while day <= END:
        if day.weekday() >= 5:                      # skip weekends outright
            day += timedelta(days=1)
            continue
        book = load_bhav(day)
        if not book:
            holidays += 1
            day += timedelta(days=1)
            continue
        sessions += 1
        ds = day.strftime(DATE_FMT)
        for fn, st in state.items():
            if st['static'] is None or ds in st['dates']:
                continue
            row = book.get(SYMBOL_MAP.get(st['sym'], st['sym']))
            if not row:
                continue
            st['new'].append(','.join(st['static'] + [
                ds, row['OpnPric'], row['HghPric'], row['LwPric'], row['ClsPric'],
                str(int(float(row['TtlTradgVol'] or 0))), '0.0', '0.0']))
            st['dates'].add(ds)
        day += timedelta(days=1)

    total = 0
    for fn, st in state.items():
        if not st['new']:
            print(f'  {st["sym"]:<16} nothing to add')
            continue
        if not DRY_RUN:
            with open(os.path.join(TARGET_DIR, fn), 'a', encoding='utf-8', newline='') as f:
                f.write('\n'.join(st['new']) + '\n')
        first = st['new'][0].split(',')[st['date_idx']]
        last = st['new'][-1].split(',')[st['date_idx']]
        print(f'  {st["sym"]:<16} +{len(st["new"]):>4} rows  {first} -> {last}')
        total += len(st['new'])

    print(f'\n[bhav] {sessions} sessions used, {holidays} non-trading days skipped, '
          f'{total} rows appended')


if __name__ == '__main__':
    main()
