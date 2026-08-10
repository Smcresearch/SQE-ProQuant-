/* ══════════════════════════════════════════════════════════════════════════
   FACTSHEET EXPORT

   Builds the client-facing factsheet from whatever the dashboard currently has
   loaded — selected universe, current holdings, latest prices, latest metrics —
   and hands it to the browser's PDF printer.

   This replaces the old exportReport(), which was a bare window.print() of the
   dashboard itself: nav tabs, dark background, charts and all. The output here
   is the document, not a screenshot of the terminal.

   Everything is read at click time from DASHBOARD_DATA, so the factsheet always
   reflects the current data update — there is no stored snapshot to go stale.
   The page is static (GitHub Pages), so the PDF comes from the browser's own
   print-to-PDF rather than a server render; the layout carries @page A4 rules
   so what lands in the PDF is the factsheet, properly paginated.
   ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── PER-DASHBOARD CONFIG ──────────────────────────────────────────────
     The only block that differs between the SQE / SQE-ProQuant / SOM copies
     of this file. Everything below it is identical. */
  var CFG = {
    model:      'SQE ProQuant',
    modelLong:  'SQE ProQuant — SMC Quant Equity',
    docTitle:   'SQE ProQuant',
    siteUrl:    'https://smcresearch.github.io/SQE-ProQuant-/',
    siteLabel:  'smcresearch.github.io/SQE-ProQuant-/',
    logo:       'smc_logo.webp',
    filePrefix: 'SQE_ProQuant_Factsheet',
    // Risk/horizon labels are the approved wording from the published
    // factsheet — deliberately fixed, not derived from the data.
    riskLabel:  'High Volatility',
    horizon:    'Long Term',
    maxWeight:  '10%'
  };

  /* Per-universe wording. Each universe reports against its own 'Bench' series;
     the other index is carried alongside as a secondary reference. */
  var UNIVERSES = {
    nifty50:      { label: 'Nifty 50',     universe: 'Nifty 50 Constituents',      assetClass: 'Equity Large Cap', bench: 'Nifty 50',  refKey: 'nifty500', refName: 'Nifty 500' },
    nifty500:     { label: 'Nifty 500',    universe: 'Nifty 500 Constituents',     assetClass: 'Equity Multi Cap', bench: 'Nifty 500', refKey: 'nifty50',  refName: 'Nifty 50'  },
    total759:     { label: 'All Indices',  universe: 'All NSE Indices',            assetClass: 'Equity Multi Cap', bench: 'Nifty 500', refKey: 'nifty50',  refName: 'Nifty 50'  },
    ml_forecast:  { label: 'ML Forecast',  universe: 'All NSE Indices — ML Overlay', assetClass: 'Equity Multi Cap', bench: 'Nifty 500', refKey: 'nifty50', refName: 'Nifty 50' },
    high_quality: { label: 'High Quality', universe: 'High Quality NSE Universe',  assetClass: 'Equity Multi Cap', bench: 'Nifty 500', refKey: 'nifty50',  refName: 'Nifty 50'  }
  };

  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'];

  var SECTOR_COLORS = ['#1a73e8', '#34a853', '#fbbc04', '#ea4335', '#9c27b0',
                       '#00bcd4', '#ff5722', '#607d8b', '#795548', '#e91e63'];

  /* ── HELPERS ──────────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function num(v, dp) {
    return (v == null || isNaN(v)) ? '—' : Number(v).toFixed(dp == null ? 2 : dp);
  }
  function pct(v, dp) {
    return (v == null || isNaN(v)) ? '—' : Number(v).toFixed(dp == null ? 2 : dp) + '%';
  }
  /* Explicit sign — used where a positive number is the point being made
     (alpha, average gain), so a bare "4.20%" cannot be misread as a loss. */
  function signed(v, dp) {
    if (v == null || isNaN(v)) return '—';
    return (v >= 0 ? '+' : '') + Number(v).toFixed(dp == null ? 2 : dp) + '%';
  }
  function money(v) {
    if (v == null || isNaN(v) || v <= 0) return '—';
    return '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  /* "2020-01" → "January 2020" */
  function monthName(ym) {
    if (!ym) return '—';
    var p = String(ym).split('-');
    var m = parseInt(p[1], 10);
    return (MONTHS[m - 1] || '') + ' ' + p[0];
  }
  function addMonth(ym, n) {
    var p = String(ym).split('-');
    var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1 + n, 1);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  }

  /* ── DATA ─────────────────────────────────────────────────────────────
     Everything the factsheet prints, pulled from the live dashboard state. */
  function collect() {
    var root = window.DASHBOARD_DATA;
    if (!root) return null;

    var uKey = (typeof state !== 'undefined' && state && state.universe) || 'nifty500';
    var d = root[uKey];
    if (!d || !d.layer_metrics || !d.layer_metrics.Base) return null;

    var U = UNIVERSES[uKey] || UNIVERSES.nifty500;
    var base = d.layer_metrics.Base;
    var ex = d.exec_summary || {};
    var pick = function (key, layer) {
      var row = ex[key];
      return (row && row[layer] != null) ? row[layer] * 100 : null;
    };

    /* Rows carrying the 'Stock' placeholder are padding in the source
       spreadsheet, not positions. */
    var portfolio = (d.current_portfolio || []).filter(function (h) {
      return h.clean_symbol && h.clean_symbol !== 'Stock';
    });

    /* Sector weights, heaviest first. */
    var secMap = {};
    portfolio.forEach(function (h) {
      var s = h.sector || 'Unclassified';
      secMap[s] = (secMap[s] || 0) + (h.weight || 0) * 100;
    });
    var sectors = Object.keys(secMap).map(function (s) {
      return { name: s, wt: secMap[s] };
    }).sort(function (a, b) { return b.wt - a.wt; });

    /* Concentration — stated in the risk section, so it has to be the real
       number for this portfolio, not a fixed one. */
    var top10 = portfolio.map(function (h) { return (h.weight || 0) * 100; })
      .sort(function (a, b) { return b - a; })
      .slice(0, 10)
      .reduce(function (a, b) { return a + b; }, 0);

    var months = (d.equity_curves && d.equity_curves.months) || [];
    var inception = months.length ? months[0] : null;
    var lastMonth = months.length ? months[months.length - 1] : null;

    /* The header stamp and the factsheet must agree on "as of when". */
    var lastUpdate = root.last_update || '';
    var lastUpdateFmt = lastUpdate;
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(lastUpdate);
    if (m) {
      lastUpdateFmt = MONTHS[parseInt(m[2], 10) - 1] + ' ' + m[3] + ', ' + m[1];
      if (!lastMonth) lastMonth = m[1] + '-' + m[2];
    }

    /* Benchmark for this universe, plus the other index as a reference. */
    var refUni = root[U.refKey];
    var refCagr = (refUni && refUni.exec_summary && refUni.exec_summary.CAGR &&
                   refUni.exec_summary.CAGR.Bench != null)
      ? refUni.exec_summary.CAGR.Bench * 100 : null;

    return {
      uKey: uKey,
      U: U,
      portfolio: portfolio,
      sectors: sectors,
      top10: top10,
      inception: inception,
      lastMonth: lastMonth,
      lastRebalance: lastMonth,
      nextRebalance: lastMonth ? addMonth(lastMonth, 1) : null,
      lastUpdate: lastUpdate,
      lastUpdateFmt: lastUpdateFmt,
      M: {
        CAGR:         base.CAGR,
        Total_Return: base.Total_Return,
        Volatility:   base.Volatility,
        Sharpe:       base.Sharpe,
        Sortino:      base.Sortino,
        Calmar:       base.Calmar,
        Max_DD:       base.Max_DD,
        Win_Rate:     base.Win_Rate,
        Avg_Gain:     base.Avg_Gain,
        Avg_Loss:     base.Avg_Loss,
        Bench_CAGR:   pick('CAGR', 'Bench'),
        Ref_CAGR:     refCagr,
        Alpha:        pick('Alpha vs Bench', 'Base'),
        Best_Month:   pick('Best Month', 'Base'),
        Worst_Month:  pick('Worst Month', 'Base'),
        VaR_95:       pick('VaR 95%', 'Base')
      }
    };
  }

  /* ── MARKUP ───────────────────────────────────────────────────────────── */
  function sectorRows(sectors) {
    return sectors.map(function (s, i) {
      var c = SECTOR_COLORS[i % SECTOR_COLORS.length];
      return '<div class="alloc-row"><span class="alloc-name">' + esc(s.name) +
        '</span><div class="alloc-track"><div class="alloc-fill" style="width:' +
        s.wt.toFixed(1) + '%;background:' + c + '"></div></div><span class="alloc-pct">' +
        s.wt.toFixed(1) + '%</span></div>';
    }).join('\n');
  }

  function holdingRows(portfolio) {
    return portfolio.map(function (h, i) {
      var chg = h.change_pct;
      var cls = (chg == null || isNaN(chg)) ? '' : (chg >= 0 ? 'g' : 'r');
      var chgS = (chg == null || isNaN(chg)) ? '—' : signed(chg);
      var badge = h.status === 'Added' ? ' <span class="badge-new">NEW</span>' : '';
      return '<tr><td class="c">' + (i + 1) + '</td><td class="sym">' +
        esc(h.clean_symbol) + badge + '</td><td>' + esc(h.sector) +
        '</td><td class="mono b">' + num((h.weight || 0) * 100, 1) + '%</td><td class="mono">' +
        money(h.ltp) + '</td><td class="' + cls + ' mono">' + chgS + '</td></tr>';
    }).join('\n');
  }

  function buildHTML(F) {
    var M = F.M, U = F.U;
    var n = F.portfolio.length;
    var logoUrl = new URL(CFG.logo, location.href).href;
    var title = CFG.filePrefix + '_' + U.label.replace(/\s+/g, '') +
                (F.lastMonth ? '_' + F.lastMonth : '');

    return '<!DOCTYPE html>\n<html lang="en">\n<head>\n' +
'<meta charset="UTF-8">\n' +
'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' +
/* Chrome names the saved PDF after the document title. */
'<title>' + esc(title) + '</title>\n' +
'<meta name="description" content="Official factsheet for the ' + esc(CFG.modelLong) + ' portfolio.">\n' +
'<link rel="preconnect" href="https://fonts.googleapis.com">\n' +
'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Roboto+Mono:wght@400;500&display=swap">\n' +
'<style>\n' + CSS + '</style>\n</head>\n<body>\n<div class="wrap">\n' +

/* ─────────── PAGE 1 ─────────── */
'<div class="card">' +
  '<div class="hdr-logo-bar"><img class="logo" src="' + esc(logoUrl) + '" alt="SMC Research"></div>' +
  '<div class="hdr">' +
    '<div class="tag">Factsheet</div>' +
    '<h1>' + esc(CFG.model) + '</h1>' +
    '<p class="sub">SMC Quant Equity — ' + esc(U.label) + ' Portfolio</p>' +
    '<div class="pills">' +
      '<div class="pill"><div class="v green">' + pct(M.CAGR) + '</div><div class="l">CAGR</div></div>' +
      '<div class="pill"><div class="v green">' + pct(M.Total_Return, 1) + '</div><div class="l">Total Return</div></div>' +
      '<div class="pill"><div class="chip">' + esc(CFG.riskLabel) + '</div><div class="l" style="margin-top:4px">Risk Level</div></div>' +
      '<div class="pill"><div class="chip">' + esc(CFG.horizon) + '</div><div class="l" style="margin-top:4px">Horizon</div></div>' +
    '</div>' +
    '<p class="ts">Last updated: ' + esc(F.lastUpdateFmt) + ' &nbsp;·&nbsp; <a href="' + CFG.siteUrl + '">View Live Dashboard →</a></p>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Portfolio Overview</div>' +
    '<div class="ig">' +
      '<div class="ic"><div class="k">Portfolio Type</div><div class="v">Thematic / Quant</div></div>' +
      '<div class="ic"><div class="k">Constituents</div><div class="v">Indian Stocks (NSE)</div></div>' +
      '<div class="ic"><div class="k">Asset Class</div><div class="v">' + esc(U.assetClass) + '</div></div>' +
      '<div class="ic"><div class="k">Universe</div><div class="v">' + esc(U.universe) + '</div></div>' +
      '<div class="ic"><div class="k">No. of Stocks</div><div class="v b">' + n + '</div></div>' +
      '<div class="ic"><div class="k">Launch Period</div><div class="v">' + esc(monthName(F.inception)) + '</div></div>' +
      '<div class="ic"><div class="k">CAGR (Portfolio)</div><div class="v g">' + pct(M.CAGR) + '</div></div>' +
      '<div class="ic"><div class="k">CAGR (' + esc(U.bench) + ')</div><div class="v b">' + pct(M.Bench_CAGR) + '</div></div>' +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Portfolio Rationale</div>' +
    '<div class="rat">' +
      '<strong>' + esc(CFG.model) + '</strong> is a concentrated, research-backed equity portfolio ' +
      'designed for <strong>long-term wealth creation</strong>. It aims to deliver superior ' +
      'risk-adjusted returns by investing in a select basket of high-quality Indian stocks ' +
      'drawn from the ' + esc(U.universe) + '.' +
      '<ul>' +
        '<li>Stocks are selected using a <strong>proprietary quantitative model</strong> developed ' +
        "by SMC Research that evaluates each stock's risk-return profile relative to the broader market</li>" +
        '<li>The portfolio holds <strong>' + n + ' high-conviction positions</strong>, with individual ' +
        'position sizes capped at <strong>' + esc(CFG.maxWeight) + '</strong> to control single-stock risk</li>' +
        '<li>Every month, the portfolio is <strong>systematically rebalanced</strong> to capture ' +
        'new opportunities and manage risk — there is no discretionary or emotional decision-making</li>' +
        '<li>The model has consistently generated <strong>alpha over the ' + esc(U.bench) + ' benchmark</strong> ' +
        'since inception, with a disciplined focus on both upside capture and downside protection</li>' +
      '</ul>' +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Rebalance Schedule</div>' +
    '<div class="reb">' +
      '<div class="ri"><div class="k">Frequency</div><div class="v">Monthly</div></div>' +
      '<div class="ri"><div class="k">Rebalance Day</div><div class="v">1st Trading Day</div></div>' +
      '<div class="ri"><div class="k">Last Rebalance</div><div class="v">' + esc(monthName(F.lastRebalance)) + '</div></div>' +
      '<div class="ri"><div class="k">Next Rebalance</div><div class="v">' + esc(monthName(F.nextRebalance)) + '</div></div>' +
      '<div class="ri"><div class="k">Managed By</div><div class="v" style="font-size:12px">SMC Research</div></div>' +
    '</div>' +
  '</div>' +
'</div>' +

/* ─────────── PAGE 2 ─────────── */
'<div class="card brk">' +
  '<div class="sec">' +
    '<div class="sec-t">Performance &amp; Risk Metrics</div>' +
    '<div class="mg">' +
      '<div>' +
        '<div class="mr"><span class="k">CAGR (Portfolio)</span><span class="v g">' + pct(M.CAGR) + '</span></div>' +
        '<div class="mr"><span class="k">CAGR (' + esc(U.bench) + ' &mdash; Benchmark)</span><span class="v n">' + pct(M.Bench_CAGR) + '</span></div>' +
        '<div class="mr"><span class="k">CAGR (' + esc(U.refName) + ' &mdash; Reference)</span><span class="v n">' + pct(M.Ref_CAGR) + '</span></div>' +
        '<div class="mr"><span class="k">Total Return</span><span class="v g">' + pct(M.Total_Return) + '</span></div>' +
        '<div class="mr"><span class="k">Alpha vs ' + esc(U.bench) + '</span><span class="v ' + (M.Alpha >= 0 ? 'g' : 'r') + '">' + signed(M.Alpha) + '</span></div>' +
        '<div class="mr"><span class="k">Annualised Volatility</span><span class="v n">' + pct(M.Volatility) + '</span></div>' +
        '<div class="mr"><span class="k">Sharpe Ratio</span><span class="v g">' + num(M.Sharpe) + '</span></div>' +
        '<div class="mr"><span class="k">Sortino Ratio</span><span class="v g">' + num(M.Sortino) + '</span></div>' +
        '<div class="mr"><span class="k">Calmar Ratio</span><span class="v g">' + num(M.Calmar) + '</span></div>' +
      '</div>' +
      '<div>' +
        '<div class="mr"><span class="k">Max Drawdown</span><span class="v r">' + pct(M.Max_DD) + '</span></div>' +
        '<div class="mr"><span class="k">Win Rate (Monthly)</span><span class="v g">' + pct(M.Win_Rate, 1) + '</span></div>' +
        '<div class="mr"><span class="k">Avg Monthly Gain</span><span class="v g">' + signed(M.Avg_Gain) + '</span></div>' +
        '<div class="mr"><span class="k">Avg Monthly Loss</span><span class="v r">' + pct(M.Avg_Loss) + '</span></div>' +
        '<div class="mr"><span class="k">Best Month</span><span class="v g">' + signed(M.Best_Month) + '</span></div>' +
        '<div class="mr"><span class="k">Worst Month</span><span class="v r">' + pct(M.Worst_Month) + '</span></div>' +
        '<div class="mr"><span class="k">VaR (95%, Monthly)</span><span class="v r">' + pct(M.VaR_95) + '</span></div>' +
        '<div class="mr"><span class="k">Live Since</span><span class="v n">' + esc(monthName(F.inception)) + '</span></div>' +
      '</div>' +
    '</div>' +
  '</div>' +
  '<div class="sec">' +
    '<div class="sec-t">Sector Allocation</div>' +
    sectorRows(F.sectors) +
  '</div>' +
'</div>' +

/* ─────────── PAGE 3 ─────────── */
'<div class="card brk">' +
  '<div class="sec">' +
    '<div class="sec-t">Current Holdings &mdash; ' + n + ' Stocks &middot; ' + esc(monthName(F.lastMonth)) + '</div>' +
    '<div style="overflow-x:auto"><table>' +
      '<thead><tr><th>#</th><th>Stock</th><th>Sector</th><th>Weight</th><th>LTP (₹)</th><th>Day Chg</th></tr></thead>' +
      '<tbody>' + holdingRows(F.portfolio) + '</tbody>' +
    '</table></div>' +
  '</div>' +
'</div>' +

/* ─────────── PAGE 4 ─────────── */
'<div class="card brk">' +
  '<div class="sec">' +
    '<div class="sec-t">How It Works</div>' +
    '<div class="ig" style="grid-template-columns:repeat(4,1fr)">' +
      step('📊', 'Step 1', 'SMC Research runs the proprietary quant model every month') +
      step('📋', 'Step 2', 'Updated portfolio with buy/sell actions published on the dashboard') +
      step('💼', 'Step 3', 'Execute the rebalance trades at the start of each month') +
      step('📈', 'Step 4', 'Hold for 3–5 years for best risk-adjusted returns') +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Key Risk Factors</div>' +
    '<div class="rg">' +
      risk('Market Risk', 'Equity prices can decline sharply due to macroeconomic, geopolitical or ' +
        'company-specific factors. The portfolio has seen a maximum drawdown of ' + pct(M.Max_DD) +
        ' over the backtest period.') +
      risk('Concentration Risk', 'The portfolio holds ' + n + ' stocks, but is top-heavy — the largest ' +
        'positions are capped at ' + esc(CFG.maxWeight) + ' each and the top 10 holdings account for roughly ' +
        num(F.top10, 0) + '% of the portfolio. Sector concentration may arise during certain market phases.') +
      risk('Model Risk', 'Past performance is not a guarantee of future results. Quantitative models ' +
        'may underperform during regime changes or unprecedented market events.') +
      risk('Liquidity Risk', 'All constituents are NSE-listed. As the universe spans mid and small cap ' +
        'companies alongside large caps, some holdings may trade with lower volumes, and liquidity ' +
        'can be temporarily limited during extreme market stress.') +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Definitions and Disclosures</div>' +
    '<div style="font-size:11px;line-height:1.75;margin-bottom:16px">' +
      '<p style="margin-bottom:10px"><strong style="color:var(--pri)">CAGR</strong> — Compound Annual Growth Rate is a measure of the growth of a ' +
      'portfolio. Returns generated each year differ; CAGR expresses them as the single annual ' +
      'rate that would produce the same terminal value over the period. For example, a portfolio ' +
      'returning 5%, 15% and &minus;7% over three years has a CAGR of 3.94%. In this factsheet CAGR ' +
      'is computed on backtested model data from ' + esc(monthName(F.inception)) + ' onwards.</p>' +
      '<p style="margin-bottom:10px"><strong style="color:var(--pri)">Volatility Label</strong> — Daily changes in stock prices cause fluctuation in the ' +
      'value of your investment. Each portfolio is categorised into one of three buckets &mdash; ' +
      'High, Medium or Low Volatility &mdash; by comparing the portfolio&rsquo;s volatility against ' +
      "that of the Nifty 100 Index. This portfolio's annualised volatility is " + pct(M.Volatility) + ', ' +
      'placing it in the <strong>' + esc(CFG.riskLabel) + '</strong> bucket. High Volatility means changes ' +
      'in your investment value can be sudden and significant.</p>' +
      '<p style="margin-bottom:10px"><strong style="color:var(--pri)">Investment Horizon</strong> — The manager&rsquo;s recommended holding duration. ' +
      'Short Term: &lt;1 year. Medium Term: 1&ndash;3 years. Long Term: &gt;3 years. This portfolio is ' +
      'recommended as <strong>' + esc(CFG.horizon) + '</strong>.</p>' +
      '<p style="margin-bottom:10px"><strong style="color:var(--pri)">Asset Class</strong> — Constituents are selected from a universe defined by the ' +
      'manager, and that universe is labelled the Asset Class. All NSE-listed stocks are ranked in ' +
      'decreasing order of market capitalisation: ranks 1&ndash;100 are Large Cap, 101&ndash;250 are Mid Cap, ' +
      'and above 250 are Small Cap. This portfolio is <strong>' + esc(U.assetClass) + '</strong>.</p>' +
      '<p style="margin-bottom:10px"><strong style="color:var(--pri)">Rebalance</strong> — The process of periodically reviewing and updating the ' +
      'constituents of a portfolio, so that the holdings continue to reflect the underlying strategy. ' +
      'This portfolio is rebalanced <strong>monthly</strong>, on the first trading day of each month.</p>' +
      '<p style="margin-bottom:10px"><strong style="color:var(--pri)">Holdings Distribution</strong> — Constituents are grouped into segments, and the ' +
      'weight of a segment is the sum of the weights of all constituents in it. For example, if four ' +
      'constituents of 10% each are Large Cap, the Large Cap segment weight is 40%.</p>' +
      '<p><strong style="color:var(--pri)">Benchmark</strong> — Portfolio performance in this factsheet is compared against the ' +
      '<strong>' + esc(U.bench) + '</strong> (CAGR ' + pct(M.Bench_CAGR) + ' over the same period), which is the ' +
      'index designated for the ' + esc(U.assetClass) + ' asset class and is therefore the appropriate ' +
      'comparison for this portfolio. The <strong>' + esc(U.refName) + '</strong> (CAGR ' + pct(M.Ref_CAGR) + ') ' +
      'is shown alongside as a secondary broad-market reference only. Alpha is stated against the ' +
      esc(U.bench) + '.</p>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px 28px;font-size:11px;line-height:1.7">' +
      '<div><strong>CAGR:</strong> Compound Annual Growth Rate — annualised return over the full period.</div>' +
      '<div><strong>Sharpe Ratio:</strong> Risk-adjusted return per unit of total volatility.</div>' +
      '<div><strong>Sortino Ratio:</strong> Risk-adjusted return penalising only downside deviation.</div>' +
      '<div><strong>Calmar Ratio:</strong> CAGR divided by maximum drawdown.</div>' +
      '<div><strong>Max Drawdown:</strong> Largest peak-to-trough decline during the period.</div>' +
      '<div><strong>Win Rate:</strong> Percentage of months with positive returns.</div>' +
      '<div><strong>Alpha:</strong> Portfolio CAGR minus ' + esc(U.bench) + ' benchmark CAGR.</div>' +
      '<div><strong>VaR (95%):</strong> Worst expected monthly loss at 95% confidence.</div>' +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">General Investment Disclosure</div>' +
    '<div class="disc">' +
      '<strong>⚠ IMPORTANT:</strong> This factsheet is for <strong>informational purposes only</strong> ' +
      'and does not constitute investment advice, solicitation, or a recommendation to buy ' +
      'or sell any securities. Past performance is not indicative of future results. ' +
      'Investments in the securities market are subject to market risks. Read all related ' +
      'documents carefully before investing.<br><br>' +
      'The performance data shown is based on a quantitative model simulation. Live ' +
      'performance may differ from model results due to transaction costs, taxes (STT, GST), ' +
      'impact cost, and execution timing. The portfolio is rebalanced monthly at month-open ' +
      'prices. <strong>All returns, CAGR and risk figures shown in this factsheet are derived ' +
      'from backtested model data covering ' + esc(monthName(F.inception)) + ' onwards, and do not represent the ' +
      'returns of an actual live-traded portfolio.</strong> Backtested results are hypothetical, ' +
      'are computed with the benefit of hindsight, and have inherent limitations. They have not ' +
      'been validated by an independent chartered accountant, nor verified by the Past Risk and ' +
      'Return Verification Agency (PaRRVA) or any other agency recognised by SEBI.<br><br>' +
      'The volatility label (High/Medium/Low) is determined by comparing the portfolio&rsquo;s ' +
      'daily volatility against the Nifty 100 Index. High Volatility means that changes in ' +
      'your investment value can be sudden and significant.' +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Risk Disclosure</div>' +
    '<div class="disc">' +
      'Investing in securities involves various types of risk that may impact your investment. ' +
      'Key risks affecting all asset classes include changes in: market volatility; general ' +
      'market conditions; trading volumes, liquidity and settlement periods; interest rates; ' +
      'the rate of inflation; domestic and global political, economic and financial ' +
      'developments; and policies, legal or regulatory frameworks set by government and other ' +
      'appropriate authorities.<br><br>' +
      '<strong>Risks relating to equity and equity-linked investments:</strong> equity shares and ' +
      'equity-related instruments are volatile and prone to price fluctuation on a daily basis. ' +
      'Prices may be affected by trading volume volatility, currency exchange rates, company ' +
      'specific news and rumours, and other factors. <strong>Mid cap and small cap stocks generally ' +
      'exhibit higher volatility than large cap stocks.</strong> As this portfolio draws from the ' +
      esc(U.universe) + ', a meaningful portion of the holdings may fall in the mid and small cap ' +
      'segments at any given time.<br><br>' +
      'In light of the risks involved, you should transact in securities only after understanding ' +
      'the associated risks. Please consider and assess all risk factors and your own risk ' +
      'tolerance before making investment decisions.' +
    '</div>' +
  '</div>' +

  '<div class="sec">' +
    '<div class="sec-t">Manager Disclosure</div>' +
    '<div class="disc">' +
      '<strong>SMC Global Securities Ltd.</strong> is registered with SEBI as a Research Analyst, ' +
      'with its registered office at 11/6B, Shanti Chamber, Pusa Road, New Delhi &ndash; 110005. ' +
      'Registration granted by SEBI and certification from NISM in no way guarantee performance ' +
      'of the intermediary or provide any assurance of returns to investors.<br><br>' +
      'The content and data available in this material, including index values, return numbers ' +
      'and rationale, are for information and illustration purposes only. Charts and performance ' +
      'numbers do not include the impact of transaction fees and other related costs. Past ' +
      'performance does not guarantee future returns and the performance of the portfolio is ' +
      'subject to market risk. Data used for the calculation of historical returns and other ' +
      'information is sourced from exchange-approved third party vendors and has neither been ' +
      'audited nor independently validated.<br><br>' +
      'Information presented in this material shall not be considered a recommendation or ' +
      'solicitation of an investment. Investors are responsible for their own investment ' +
      'decisions and for validating all information used to make those decisions.<br><br>' +
      'This document is solely for the personal information of the recipient and must not ' +
      'be used as the basis of any investment decision. Nothing in this document should be ' +
      'construed as investment or financial advice. The report and information contained ' +
      'herein may not be altered, reproduced, or redistributed without prior written consent.' +
    '</div>' +
  '</div>' +
'</div>' +

'<div class="ft" style="margin-bottom:0">' +
  '<strong>SMC Research — Moneywise. Be Wise.</strong><br>' +
  esc(CFG.model) + ' · ' + esc(U.label) + ' Portfolio · Monthly Rebalanced<br>' +
  '<a href="' + CFG.siteUrl + '">' + esc(CFG.siteLabel) + '</a>' +
  ' &nbsp;·&nbsp; Data as of: ' + esc(F.lastUpdateFmt) +
'</div>' +

'</div>\n' +
'<button class="pbtn no-print" onclick="window.print()">🖨️ Print / Save PDF</button>\n' +
/* Hold the print dialog until the logo and webfonts have actually landed —
   printing early snapshots the page mid-load and the header comes out bare. */
'<script>\n' +
'window.addEventListener("load", function () {\n' +
'  var fonts = document.fonts ? document.fonts.ready : Promise.resolve();\n' +
'  fonts.catch(function () {}).then(function () {\n' +
'    setTimeout(function () { window.focus(); window.print(); }, 300);\n' +
'  });\n' +
'});\n' +
'<\/script>\n' +
'</body>\n</html>';
  }

  function step(icon, k, text) {
    return '<div class="ic" style="text-align:center">' +
      '<div style="font-size:22px;margin-bottom:6px">' + icon + '</div>' +
      '<div class="k">' + k + '</div>' +
      '<div style="font-size:11.5px;color:var(--sub);margin-top:4px">' + text + '</div></div>';
  }
  function risk(k, text) {
    return '<div class="rc"><div class="rk">' + k + '</div><p>' + text + '</p></div>';
  }

  /* ── STYLES ───────────────────────────────────────────────────────────
     Kept as one string so the generated document is fully self-contained —
     it has to survive being opened in a blank window with no stylesheet of
     its own. Mirrors the print layout used by generate_factsheet.py. */
  var CSS = [
'*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}',
':root{--pri:#0f2b54;--pri2:#1565c0;--acc:#16c784;--red:#ea3943;--bg:#f3f6fb;--bdr:#dde3ef;--txt:#1a1a2e;--sub:#6b7a99;--wh:#fff;--sh:0 2px 16px rgba(15,43,84,.08);--r:12px;--f:\'Inter\',system-ui,sans-serif;--m:\'Roboto Mono\',monospace}',
'html{scroll-behavior:smooth}',
'body{font-family:var(--f);background:var(--bg);color:var(--txt);font-size:13px;line-height:1.65;-webkit-font-smoothing:antialiased}',
'@page{size:A4;margin:10mm 9mm 12mm}',
'@media print{',
/* Chrome drops background colours when printing unless told otherwise —
   without this the blue header, sector bars and metric colours print white. */
'  *{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}',
'  html,body{background:#fff;font-size:9.5px}',
'  .no-print{display:none!important}',
'  .wrap{max-width:none;padding:0}',
'  .brk{page-break-before:always}',
'  .card{box-shadow:none;margin-bottom:0;border:none;border-radius:0;overflow:visible}',
'  .sec{break-inside:auto;padding:14px 22px}',
'  .sec-t{break-after:avoid}',
'  .ic,.ri,.mr,.rc,.sb{break-inside:avoid}',
'  .rat{break-inside:avoid}',
'  table{break-inside:auto;font-size:8.6px!important}',
'  thead{display:table-header-group}',
'  tr{break-inside:avoid;break-after:auto}',
/* Tighten rows so a full book of holdings fits one page instead of spilling a
   handful onto a near-empty one. !important is required: the base table rules
   are declared later and would otherwise win on equal specificity. */
'  thead th,td{padding:4.1px 8px!important;font-size:8.6px!important}',
'  tr:hover td{background:transparent!important}',
'  .hdr{padding:20px 30px 22px}',
'  .disc{break-inside:auto}',
'  a{text-decoration:none;color:inherit}',
'}',
'.wrap{max-width:880px;margin:0 auto;padding:20px 16px 80px}',
'.card{background:var(--wh);border-radius:var(--r);box-shadow:var(--sh);margin-bottom:20px;overflow:hidden}',
'.hdr-logo-bar{background:#ffffff;padding:20px 40px;text-align:center;border-bottom:1px solid var(--bdr);display:flex;justify-content:center;align-items:center}',
'.logo{display:block;height:45px;max-width:100%;object-fit:contain}',
'.hdr{background:linear-gradient(135deg,#0f2b54 0%,#1565c0 60%,#1e88e5 100%);color:#fff;padding:28px 40px 30px;text-align:center;position:relative}',
'.hdr::after{content:\'\';position:absolute;inset:0;background:url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cpath d=\'M0 30h60M30 0v60\' stroke=\'%23fff\' stroke-opacity=\'.03\' stroke-width=\'1\'/%3E%3C/svg%3E");pointer-events:none}',
'.hdr>*{position:relative;z-index:1}',
'.tag{display:inline-block;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);border-radius:20px;padding:3px 14px;font-size:10px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;margin-bottom:14px}',
'.hdr h1{font-size:24px;font-weight:800;letter-spacing:-.4px;margin-bottom:6px}',
'.hdr .sub{font-size:12.5px;opacity:.75;margin-bottom:22px}',
'.pills{display:flex;justify-content:center;gap:28px;flex-wrap:wrap}',
'.pill{text-align:center}',
'.pill .v{font-size:22px;font-weight:800}',
'.pill .v.green{color:#4ade80}',
'.pill .l{font-size:10px;opacity:.65;margin-top:2px}',
'.pill .chip{display:inline-block;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22);border-radius:16px;padding:3px 12px;font-size:10.5px;font-weight:600}',
'.hdr .ts{margin-top:18px;font-size:10px;opacity:.5}',
'.hdr .ts a{color:rgba(255,255,255,.85);text-decoration:none}',
'.sec{padding:24px 32px;border-bottom:1px solid var(--bdr)}',
'.sec:last-child{border-bottom:none}',
'.sec-t{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--pri);margin-bottom:16px;display:flex;align-items:center;gap:8px}',
'.sec-t::after{content:\'\';flex:1;height:1px;background:var(--bdr)}',
'.ig{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}',
'.ic{background:var(--bg);border:1px solid var(--bdr);border-radius:8px;padding:12px 14px}',
'.ic .k{font-size:10px;color:var(--sub);font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px}',
'.ic .v{font-size:14px;font-weight:700}',
'.ic .v.g{color:var(--acc)} .ic .v.b{color:var(--pri2)} .ic .v.r{color:var(--red)}',
'.rat{background:linear-gradient(135deg,#f0f5ff 0%,#e8f5e9 100%);border:1px solid #c8d8f0;border-left:4px solid var(--pri2);border-radius:8px;padding:18px 22px;font-size:13px;line-height:1.8;color:var(--txt)}',
'.rat strong{color:var(--pri)}',
'.rat ul{margin:10px 0 0 20px}',
'.rat li{margin-bottom:6px}',
'.reb{display:flex;gap:14px;flex-wrap:wrap}',
'.ri{flex:1;min-width:130px;background:var(--bg);border:1px solid var(--bdr);border-radius:8px;padding:14px;text-align:center}',
'.ri .k{font-size:10px;color:var(--sub);font-weight:600;text-transform:uppercase;letter-spacing:.4px}',
'.ri .v{font-size:14px;font-weight:700;color:var(--pri);margin-top:4px}',
'.mg{display:grid;grid-template-columns:1fr 1fr;gap:28px}',
'@media(max-width:600px){.mg{grid-template-columns:1fr}}',
'.mr{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--bdr)}',
'.mr:last-child{border-bottom:none}',
'.mr .k{font-size:12px;color:var(--sub)}',
'.mr .v{font-size:13px;font-weight:700;font-family:var(--m)}',
'.g{color:var(--acc)!important} .r{color:var(--red)!important} .n{color:var(--txt)}',
'.alloc-row{display:flex;align-items:center;gap:10px;padding:6px 0}',
'.alloc-name{font-size:11.5px;min-width:210px;color:var(--txt)}',
'.alloc-track{flex:1;background:var(--bg);border-radius:4px;height:7px;overflow:hidden}',
'.alloc-fill{height:100%;border-radius:4px}',
'.alloc-pct{font-size:12px;font-weight:700;font-family:var(--m);min-width:42px;text-align:right}',
'table{width:100%;border-collapse:collapse;font-size:12px}',
'thead th{background:var(--pri);color:#fff;padding:9px 10px;text-align:left;font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}',
'thead th:first-child{border-radius:6px 0 0 0} thead th:last-child{border-radius:0 6px 0 0}',
'td{padding:9px 10px;border-bottom:1px solid var(--bdr)}',
'tr:last-child td{border-bottom:none}',
'tr:nth-child(even) td{background:#fafbfd}',
'tr:hover td{background:#f0f4ff}',
'.c{text-align:center;color:var(--sub);font-size:11px}',
'.sym{font-weight:700;font-size:13px;color:var(--pri)}',
'.b{font-weight:700}',
'.mono{font-family:var(--m)}',
'.badge-new{display:inline-block;background:#e3f2fd;color:#1565c0;font-size:8px;font-weight:800;border-radius:3px;padding:1px 5px;margin-left:4px;vertical-align:middle;letter-spacing:.3px}',
'.rg{display:grid;grid-template-columns:1fr 1fr;gap:14px}',
'@media(max-width:600px){.rg{grid-template-columns:1fr}}',
'.rc{background:var(--bg);border:1px solid var(--bdr);border-radius:8px;padding:14px 16px}',
'.rc .rk{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--red);margin-bottom:5px}',
'.rc p{font-size:11px;color:var(--sub);line-height:1.6}',
'.disc{background:#f9fafc;border:1px solid var(--bdr);border-radius:8px;padding:16px 20px;font-size:10px;color:var(--sub);line-height:1.75}',
'.disc strong{color:var(--red)}',
'.ft{background:var(--pri);color:rgba(255,255,255,.65);text-align:center;padding:18px 32px;font-size:10.5px;border-radius:var(--r)}',
'.ft strong{color:#fff} .ft a{color:rgba(255,255,255,.85);text-decoration:none}',
'.pbtn{position:fixed;bottom:20px;right:20px;background:var(--pri2);color:#fff;border:none;border-radius:50px;padding:11px 22px;font-size:12px;font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(21,101,192,.35);font-family:var(--f);z-index:999;transition:transform .2s}',
'.pbtn:hover{transform:translateY(-2px)}',
'@media(max-width:600px){.sec{padding:18px 16px}.hdr{padding:24px 18px 22px}.alloc-name{min-width:140px}.rg,.ig{grid-template-columns:1fr}}'
  ].join('\n');

  /* ── ENTRY POINT ──────────────────────────────────────────────────────── */
  function exportFactsheet() {
    var F;
    try {
      F = collect();
    } catch (e) {
      console.error('[factsheet] could not read dashboard data', e);
      F = null;
    }
    if (!F) {
      alert('Factsheet unavailable — the dashboard data has not finished loading. Please try again in a moment.');
      return;
    }
    if (!F.portfolio.length) {
      alert('Factsheet unavailable — no holdings found for the ' + F.U.label + ' universe.');
      return;
    }

    var win = window.open('', '_blank');
    if (!win) {
      alert('The factsheet opens in a new tab — please allow pop-ups for this site and click Export Report again.');
      return;
    }
    win.document.open();
    win.document.write(buildHTML(F));
    win.document.close();
  }

  /* Replaces the plain window.print() defined in app.js. index.html calls
     exportReport() via onclick, which resolves off window at click time, so
     overriding here is enough — no markup change needed. */
  window.exportReport = exportFactsheet;
  window.exportFactsheet = exportFactsheet;
})();
