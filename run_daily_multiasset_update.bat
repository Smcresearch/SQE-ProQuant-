@echo off
REM ==============================================================================
REM  Automated Daily Update — SQE MultiAsset ProQuant (Equity + Gold + Silver)
REM  Chained off run_daily_sqe_update.bat (17:30 IST), which refreshes the equity
REM  CSVs first and then calls this with --noprices. Do NOT give this its own
REM  Task Scheduler trigger: two concurrent runs of the price fetchers append the
REM  same session twice and every backtest then dies on a duplicate date.
REM  Publishes to: https://smcresearch.github.io/SQE-MultiAsset-ProQuant/
REM
REM  What "update" means here: mark the CURRENT book to the latest close, so the
REM  live month-to-date portfolio return and the benchmark return both move.
REM
REM    [1] stock + index prices   nifty50_host / nifty500_host / TOTAL_STOCKS,
REM                               plus NIFTY50_1d.csv + NIFTY500_1d.csv (benchmark)
REM    [2] bullion prices         GOLDBEES / SILVERBEES
REM    [3] dedupe                 drop duplicate-date rows before anything reads them
REM    [4] backtests              re-run the 12 books so the live month is re-marked
REM    [5] HQ variants            the 4 High Quality books, a different engine
REM    [6] build + push           data.js + holdings.js -> GitHub Pages
REM
REM  Steps [4] and [5] are not optional. The live month's port_ret / bench_ret
REM  live inside the Sharpe_Summary workbooks, so fresh CSVs alone change nothing
REM  on the site (gold/silver are the exception — those are read straight from
REM  the CSVs, which is why they kept printing while everything above them showed
REM  "-" for the whole of Sep'26).
REM
REM  Pass --noprices to skip step [1] when run_daily_sqe_update.bat has already
REM  refreshed the equity CSVs this evening. Bullion always runs: nothing else
REM  updates it.
REM
REM  Any step that fails aborts the run: a site one day stale beats a half-updated one.
REM
REM  Run by hand (PowerShell):  .\run_daily_multiasset_update.bat
REM ==============================================================================

setlocal enabledelayedexpansion
set LOGFILE=d:\Host_portfolio\daily_multiasset_update.log
set PYTHON=d:\Host_portfolio\host\Scripts\python.exe
REM Deliberately not named HOME — git reads HOME on Windows to find .gitconfig
REM and the credential helper, and the push would stop authenticating.
set ROOT=d:\Host_portfolio

set SKIPPRICES=
if /I "%~1"=="--noprices" set SKIPPRICES=1

echo. >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"
echo [START] MultiAsset Daily Update: %DATE% %TIME% >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"

cd /d "%ROOT%"

if defined SKIPPRICES (
    echo [1/6] Stock + index prices SKIPPED ^(--noprices^) >> "%LOGFILE%"
) else (
    REM  data_set_nifty5.py, data_set_nifty500.py and index_data.py were deleted
    REM  and exist nowhere on this machine; update_stocks.py (all price folders)
    REM  and update_indices.py (both indices + the CNX500 benchmark) replace all
    REM  four. This branch only runs when the bat is invoked WITHOUT --noprices,
    REM  i.e. by hand, so it failed silently for anyone who tried that.
    echo [1/6] Refreshing stock + index prices ^(incremental^) ... >> "%LOGFILE%"
    for %%S in (update_stocks.py update_indices.py) do (
        echo    -^> %%S >> "%LOGFILE%"
        "%PYTHON%" "%ROOT%\%%S" >> "%LOGFILE%" 2>&1
        if errorlevel 1 (set RC=!ERRORLEVEL! & set STEP=%%S & goto :fail)
    )
)

echo [2/6] Refreshing bullion prices ... >> "%LOGFILE%"
"%PYTHON%" "%ROOT%\update_bullion.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (set RC=!ERRORLEVEL! & set STEP=update_bullion.py & goto :fail)

echo [3/6] Dropping any duplicate-date rows from the price CSVs ... >> "%LOGFILE%"
"%PYTHON%" "%ROOT%\dedupe_stock_csvs.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (set RC=!ERRORLEVEL! & set STEP=dedupe_stock_csvs.py & goto :fail)

echo [4/6] Re-marking the book — 12 multi-asset backtests ... >> "%LOGFILE%"
"%PYTHON%" "%ROOT%\run_multiasset_backtests.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (set RC=!ERRORLEVEL! & set STEP=run_multiasset_backtests.py & goto :fail)

REM  The site carries FOUR universes but the step above only produces three:
REM  N50/N500/T759 come from som_metals.py, High Quality from
REM  SOM_hq_quarterly.py. Nothing regenerated HQ, so its workbooks sat frozen at
REM  the 31-08-2026 build and never gained a live month — the Sep'26 panel
REM  showed "-" for all four HQ variants and their benchmark while GOLDBEES and
REM  SILVERBEES still printed, those being read off the bullion CSVs directly.
echo [5/6] Re-marking the 4 High Quality bullion variants ... >> "%LOGFILE%"
"%PYTHON%" "%ROOT%\run_hq_multiasset.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (set RC=!ERRORLEVEL! & set STEP=run_hq_multiasset.py & goto :fail)

echo [6/6] Rebuilding data.js + holdings.js and pushing the site ... >> "%LOGFILE%"
"%PYTHON%" "%ROOT%\build_multiasset.py" --extract --push >> "%LOGFILE%" 2>&1
if errorlevel 1 (set RC=!ERRORLEVEL! & set STEP=build_multiasset.py & goto :fail)

echo [SUCCESS] MultiAsset Daily Update completed at %DATE% %TIME% >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"
endlocal
exit /b 0

:fail
echo [ERROR] !STEP! failed with code !RC! at %DATE% %TIME% >> "%LOGFILE%"
echo [ERROR] site NOT pushed — data left as it was >> "%LOGFILE%"
echo ======================================================== >> "%LOGFILE%"
endlocal
exit /b 1
