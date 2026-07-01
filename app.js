/* SOM Institutional Terminal - app.js */

// SQE All-Indices build: only Base SIM plus the two benchmarks. 'Bench' is this
// universe's own benchmark (Nifty 500); 'BenchN50' (Nifty 50) is injected from
// the nifty50 dataset by injectDualBenchmark().
const LAYERS = {
  Base:     { label: 'SQE',       color: '#22d3ee', cls: 'ltag-base' },
  Bench:    { label: 'Nifty 500', color: '#94a3b8', cls: 'ltag-bench' },
  BenchN50: { label: 'Nifty 50',  color: '#f59e0b', cls: 'ltag-bench' }
};
const BENCH_KEYS = ['Bench', 'BenchN50'];
const isBenchKey = (l) => BENCH_KEYS.includes(l);

let state = {
  universe: 'nifty500',
  tab: 'overview',
  heatLayer: 'Base',
  chartTypes: {
    equityOverview: 'line',
    betaChart: 'bar',
    winRateChart: 'bar',
    equityMain: 'line',
    churnAddChart: 'line',
    churnRemChart: 'line'
  }
};
const charts = {};

// Shared investment amount across the Live Portfolio and Portfolio Changes tabs.
let sharedInvestAmount = 100000;

/* ── GLOBALS ─────────────────────────────────── */
function switchUniverse(u) {
  state.universe = u;
  document.getElementById('btn-n50')?.classList.toggle('active', u === 'nifty50');
  document.getElementById('btn-n500')?.classList.toggle('active', u === 'nifty500');
  document.getElementById('btn-n759')?.classList.toggle('active', u === 'total759');
  document.getElementById('btn-ml')?.classList.toggle('active', u === 'ml_forecast');
  document.getElementById('btn-hq')?.classList.toggle('active', u === 'high_quality');
  renderTab(state.tab);
}

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + tab));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  renderTab(tab);
}

function switchChartType(id, type) {
  state.chartTypes[id] = type;
  renderTab(state.tab);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const target = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', target);
  localStorage.setItem('som-theme', target);
  renderTab(state.tab);
}

function closeModal() {
  document.getElementById('hmModal').classList.remove('open');
}

window.switchUniverse = switchUniverse;
window.switchTab = switchTab;
window.switchChartType = switchChartType;
window.toggleTheme = toggleTheme;
window.closeModal = closeModal;

// Init theme
const savedTheme = localStorage.getItem('som-theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

/* ── CHART HELPER ────────────────────────────── */
function mkChart(id, defaultType, data, options) {
  const el = document.getElementById(id);
  if (!el) return;
  if (charts[id]) { charts[id].destroy(); }

  const type = state.chartTypes[id] || defaultType;
  
  // Custom tweaks for "Dot" chart (which is just a line chart with no lines)
  if (type === 'dot') {
    data.datasets.forEach(ds => {
      ds.showLine = false;
      ds.pointRadius = 4;
    });
  } else if (type === 'line') {
    data.datasets.forEach(ds => {
      ds.showLine = true;
      ds.pointRadius = id.includes('equity') ? 0 : 2;
    });
  }

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const gridCol = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.04)';
  const tickCol = isLight ? '#475569' : '#64748b';
  const labelCol = isLight ? '#1e293b' : '#94a3b8';

  const defaults = {
    responsive: true, maintainAspectRatio: false,
    interaction: {
      intersect: false,
      mode: 'index',
    },
    plugins: { 
      legend: { labels: { color: labelCol, boxWidth: 10, font: { size: 10 } } },
      tooltip: {
        backgroundColor: isLight ? 'rgba(255, 255, 255, 0.95)' : 'rgba(10, 22, 42, 0.95)',
        titleColor: isLight ? '#06b6d4' : '#22d3ee',
        bodyColor: isLight ? '#1e293b' : '#e2e8f0',
        borderColor: isLight ? 'rgba(0, 0, 0, 0.1)' : 'rgba(34, 211, 238, 0.2)',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
        displayColors: true,
        bodyFont: { family: "'Roboto Mono', monospace", size: 12 },
        titleFont: { family: "'Inter', sans-serif", weight: 'bold', size: 14 },
        callbacks: {
          label: (context) => {
            let label = context.dataset.label || '';
            if (label) label += ': ';
            if (context.parsed.y !== null) {
              label += context.parsed.y.toFixed(2);
              if (id.includes('winRate') || id.includes('equity')) label += '%';
            }
            return label;
          }
        }
      }
    },
    scales: {
      x: { grid: { color: gridCol }, ticks: { color: tickCol, maxTicksLimit: 12 } },
      y: { grid: { color: gridCol }, ticks: { color: tickCol } }
    }
  };

  // Custom Plugin for Vertical Crosshair Line
  const verticalLinePlugin = {
    id: 'verticalLine',
    afterDraw: (chart) => {
      if (chart.tooltip?._active?.length) {
        const x = chart.tooltip._active[0].element.x;
        const yAxis = chart.scales.y;
        const ctx = chart.ctx;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, yAxis.top);
        ctx.lineTo(x, yAxis.bottom);
        ctx.lineWidth = 1;
        ctx.strokeStyle = isLight ? 'rgba(0, 0, 0, 0.2)' : 'rgba(34, 211, 238, 0.3)';
        ctx.setLineDash([5, 5]);
        ctx.stroke();
        ctx.restore();
      }
    }
  };

  charts[id] = new Chart(el.getContext('2d'), { 
    type: type === 'dot' ? 'line' : type, 
    data, 
    options: Object.assign({}, defaults, options),
    plugins: [verticalLinePlugin]
  });

  renderChartControls(id);
}

function renderChartControls(id) {
  const container = document.querySelector(`.chart-controls[data-for="${id}"]`);
  if (!container) return;

  const current = state.chartTypes[id] || 'line';
  const types = [
    { id: 'line', icon: '📈', label: 'Line' },
    { id: 'bar',  icon: '📊', label: 'Bar' },
    { id: 'dot',  icon: '●', label: 'Dots' }
  ];

  container.innerHTML = types.map(t => `
    <button class="chart-control-btn ${current === t.id ? 'active' : ''}" 
            onclick="switchChartType('${id}', '${t.id}')" 
            title="${t.label}">
      ${t.icon}
    </button>
  `).join('');
}

/* ── DATA ACCESSOR ───────────────────────────── */
function D() { return DASHBOARD_DATA[state.universe]; }
// Per-month holdings for the ACTIVE universe (holdings.js is keyed by universe).
function H() { return (typeof MONTHLY_HOLDINGS !== 'undefined' && MONTHLY_HOLDINGS[state.universe]) || {}; }

/* Inject the Nifty 50 benchmark into each portfolio universe as a 'BenchN50'
   series so the layer-iterating charts show both benchmarks. Idempotent. */
function injectDualBenchmark() {
  const n50 = DASHBOARD_DATA.nifty50;
  if (!n50) return;
  ['nifty500', 'total759', 'ml_forecast', 'high_quality'].forEach(u => {
    const t = DASHBOARD_DATA[u];
    if (!t || t.__dualBench) return;
    t.__dualBench = true;

    // Equity curve — align Nifty 50 benchmark onto this universe's month axis
    if (t.equity_curves && n50.equity_curves) {
      const byMonth = {};
      (n50.equity_curves.months || []).forEach((mo, i) => { byMonth[mo] = n50.equity_curves.Bench?.[i]; });
      t.equity_curves.BenchN50 = (t.equity_curves.months || []).map(mo => byMonth[mo] ?? null);
    }
    // Layer metrics
    if (t.layer_metrics && n50.layer_metrics) {
      t.layer_metrics.BenchN50 = n50.layer_metrics.Bench;
    }
    // Monthly detail — per-month Nifty 50 benchmark return (for heatmap + rolling calcs)
    if (Array.isArray(t.monthly_detail) && Array.isArray(n50.monthly_detail)) {
      const byMonth = {};
      n50.monthly_detail.forEach(r => { byMonth[String(r.Month).slice(0, 7)] = r.Bench; });
      t.monthly_detail.forEach(r => { r.BenchN50 = byMonth[String(r.Month).slice(0, 7)]; });
    }
  });
}

/* ── RENDER ROUTER ───────────────────────────── */
function renderTab(tab) {
  injectDualBenchmark();
  const d = D();
  if (!d) return;
  renderBacktestPeriod(d);
  if (tab === 'overview')  renderOverview(d);
  if (tab === 'heatmap')   renderHeatmaps(d);
  if (tab === 'performance') renderPerformance(d);
  if (tab === 'layers')    renderLayers(d);
  if (tab === 'churning')  renderChurning(d);
  if (tab === 'portfolio') renderPortfolio(d);
  if (tab === 'trades')    renderTrades(d);
  
  renderRegimeBadge(d);
}

/* Backtest period label — makes clear all metrics (CAGR, Sharpe, etc.) are
   computed over the strategy's backtest window (derived from the data). */
function renderBacktestPeriod(d) {
  const el = document.getElementById('backtest-period');
  if (!el) return;
  const md = (d.monthly_detail || []).filter(r => /^\d{4}-\d{2}/.test(String(r.Month)));
  if (!md.length) { el.textContent = ''; return; }
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const fmt = (m) => { const s = String(m).slice(0, 7); return MON[+s.slice(5, 7) - 1] + ' ' + s.slice(0, 4); };
  el.textContent = `Backtest: ${fmt(md[0].Month)} – ${fmt(md[md.length - 1].Month)} · ${md.length} months · all metrics (CAGR, Sharpe, etc.) are computed over this period`;
}

/* ══════════════════════════════════════════════
   OVERVIEW
══════════════════════════════════════════════ */
function renderOverview(d) {
  const base = d.layer_metrics.Base;
  const kpis = [
    { label: 'CAGR (SQE)',       val: base.CAGR,          unit: '%', color: '#22d3ee', accent: '#22d3ee' },
    { label: 'Ex-Ante Sharpe',   val: d.avg_ex_ante_sr,   unit: '',  color: '#f59e0b', accent: '#f59e0b' },
    { label: 'Max Drawdown',     val: base.Max_DD,         unit: '%', color: '#f43f5e', accent: '#f43f5e' },
    { label: 'Total Return',     val: base.Total_Return,   unit: '%', color: '#10b981', accent: '#10b981' },
    { label: 'Avg Gain (M)',     val: base.Avg_Gain,       unit: '%', color: '#8b5cf6', accent: '#8b5cf6' },
    { label: 'Avg Loss (M)',     val: base.Avg_Loss,       unit: '%', color: '#f97316', accent: '#f97316' },
    { label: 'Win Rate',         val: base.Win_Rate,       unit: '%', color: '#06b6d4', accent: '#06b6d4' },
    { label: 'Alpha vs Bench',   val: base.Alpha,          unit: '%', color: '#a78bfa', accent: '#a78bfa' }
  ];

  const row = document.getElementById('kpi-row');
  row.innerHTML = kpis.map((k, i) => `
    <div class="kpi-card" style="--accent:${k.accent}">
      <span class="kpi-label">${k.label}</span>
      <span class="kpi-value" style="color:${k.color}" id="ov-kpi-${i}">—</span>
      <span class="kpi-delta ${k.val >= 0 ? 'pos' : 'neg'}">${k.val >= 0 ? '▲' : '▼'} ${Math.abs(k.val).toFixed(2)}${k.unit}</span>
    </div>`).join('');

  kpis.forEach((k, i) => {
    if (window.countUp) {
      new window.countUp.CountUp('ov-kpi-' + i, k.val, { decimalPlaces: 2, suffix: k.unit, duration: 1.2 }).start();
    } else {
      document.getElementById('ov-kpi-' + i).textContent = k.val.toFixed(2) + k.unit;
    }
  });

  // Equity chart
  const ec = d.equity_curves;
  const datasets = Object.keys(LAYERS).map(l => ({
    label: LAYERS[l].label, data: ec[l] || [],
    borderColor: LAYERS[l].color, borderWidth: isBenchKey(l) ? 1 : 2,
    borderDash: isBenchKey(l) ? [5,4] : [],
    pointRadius: 0, tension: 0.3, fill: false
  }));
  console.log(`[Equity Overview] Rendering ${datasets.length} layers.`);

  mkChart('equityOverview', 'line', {
    labels: ec.months,
    datasets: datasets
  }, { plugins: { legend: { position: 'top' } } });

  // Sector pie
  renderSectorPie('overviewSectorPie', d.current_portfolio || []);

  // Beta bar
  const md = d.monthly_detail.slice(-12);
  mkChart('betaChart', 'bar', {
    labels: md.map(r => r.Month.slice(0, 7)),
    datasets: [{ label: 'Beta', data: md.map(r => r.Port_Beta),
      backgroundColor: 'rgba(34,211,238,0.35)', borderColor: '#22d3ee', borderWidth: 1, borderRadius: 4 }]
  }, { plugins:{legend:{display:false}}, scales:{y:{min:0,max:2,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#64748b'}},
       x:{grid:{display:false},ticks:{color:'#64748b'}}} });

  // Win rate bar — Base SIM + both benchmarks
  const layers7 = Object.keys(LAYERS);
  mkChart('winRateChart', 'bar', {
    labels: layers7.map(l => LAYERS[l].label),
    datasets: [{ label: 'Win Rate %', data: layers7.map(l => d.layer_metrics[l].Win_Rate),
      backgroundColor: layers7.map(l => LAYERS[l].color + '55'),
      borderColor: layers7.map(l => LAYERS[l].color), borderWidth: 1, borderRadius: 4 }]
  }, { indexAxis: 'y', plugins:{legend:{display:false}},
       scales:{x:{min:0,max:100,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#64748b'}},
               y:{grid:{display:false},ticks:{color:'#94a3b8',font:{size:10}}}} });
}

/* ══════════════════════════════════════════════
   HEATMAPS — all 8 layers with layer tabs
══════════════════════════════════════════════ */
function renderHeatmaps(d) {
  // Build layer tabs
  const tabsEl = document.getElementById('heatmap-layer-tabs');
  if (!tabsEl.hasChildNodes()) {
    Object.keys(LAYERS).forEach(l => {
      const btn = document.createElement('button');
      btn.className = 'layer-tab-btn' + (l === state.heatLayer ? ' active' : '');
      btn.textContent = LAYERS[l].label;
      btn.onclick = () => {
        state.heatLayer = l;
        tabsEl.querySelectorAll('.layer-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderHeatmap(d, l);
      };
      tabsEl.appendChild(btn);
    });
  }
  renderHeatmap(d, state.heatLayer);
}

function renderHeatmap(d, layer) {
  const container = document.getElementById('heatmap-container');
  const md = d.monthly_detail;
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  // The LAST monthly row is the LIVE / upcoming month: its basket is formed but the
  // month has not been traded yet, so it has no realized return (only a tiny entry
  // cost). Mark it as live rather than rendering it as a finished cell.
  const liveM = md.length ? String(md[md.length - 1].Month).slice(0, 7) : null;

  // Build year/month grid from monthly_detail (excluding the live month)
  const grid = {};
  md.forEach(row => {
    const m = String(row.Month).slice(0, 7);
    if (!m || m.length < 7 || m === liveM) return;
    const yr = m.slice(0, 4), mo = parseInt(m.slice(5, 7)) - 1;
    if (!grid[yr]) grid[yr] = new Array(12).fill(null);
    const val = row[layer];
    if (val != null) grid[yr][mo] = +(val * 100).toFixed(2);
  });
  // Ensure the live month's year row exists so its cell can render.
  if (liveM && !grid[liveM.slice(0, 4)]) grid[liveM.slice(0, 4)] = new Array(12).fill(null);

  const years = Object.keys(grid).sort((a, b) => +b - +a);

  let html = '<div class="heatmap-wrap"><div class="heatmap-grid">';
  html += '<div class="hm-head">Year</div>' + MONTHS.map(m => `<div class="hm-head">${m}</div>`).join('')
        + '<div class="hm-head">Total</div>';

  years.forEach(yr => {
    html += `<div class="hm-year">${yr}</div>`;
    grid[yr].forEach((val, mi) => {
      const monthStr = `${yr}-${String(mi+1).padStart(2,'0')}`;
      if (monthStr === liveM) {
        html += `<div class="hm-cell" style="background:rgba(56,189,248,0.16);color:#38bdf8;font-weight:700"
          onclick="openHeatModal('${monthStr}')" title="${monthStr}: LIVE basket — this month is not traded yet (no realized return)">●</div>`;
      } else if (val === null) {
        html += `<div class="hm-cell empty" title="${monthStr}: no data (before strategy inception)">–</div>`;
      } else {
        const bg = heatColor(val);
        const fg = Math.abs(val) > 4 ? '#fff' : 'rgba(255,255,255,0.5)';
        html += `<div class="hm-cell" style="background:${bg};color:${fg}"
          onclick="openHeatModal('${monthStr}')" title="${monthStr}: ${val}%">
          ${val > 0 ? '+' : ''}${val}
        </div>`;
      }
    });

    // Year total: compound the available monthly returns
    const months = grid[yr].filter(v => v !== null);
    if (months.length) {
      const total = +((months.reduce((acc, v) => acc * (1 + v / 100), 1) - 1) * 100).toFixed(2);
      const bg = heatColor(total);
      const fg = Math.abs(total) > 4 ? '#fff' : 'rgba(255,255,255,0.75)';
      html += `<div class="hm-cell hm-total" style="background:${bg};color:${fg}"
        title="${yr} total return: ${total}%">
        ${total > 0 ? '+' : ''}${total}
      </div>`;
    } else {
      html += `<div class="hm-cell empty"></div>`;
    }
  });

  html += '</div></div>';
  container.innerHTML = html;
}

function heatColor(val) {
  if (val > 0) return `rgba(16,185,129,${Math.min(val/10, 0.85)})`;
  return `rgba(244,63,94,${Math.min(Math.abs(val)/10, 0.85)})`;
}

function openHeatModal(monthStr) {
  const d = D();
  const row = d.monthly_detail.find(r => String(r.Month).slice(0,7) === monthStr);
  if (!row) return;

  // The last monthly row is the LIVE/upcoming month — basket formed, not traded yet.
  const liveMonth = d.monthly_detail.length ? String(d.monthly_detail[d.monthly_detail.length - 1].Month).slice(0, 7) : '';
  const isLive = monthStr === liveMonth;

  document.getElementById('modal-month').textContent = monthStr + (isLive ? '  ·  LIVE (not yet traded)' : '');
  const benchVal = (isLive || row.Bench == null) ? null : +(row.Bench * 100).toFixed(2);

  // Benchmark return for the same month from BOTH indices, regardless of universe
  const benchOf = (u) => {
    const r = DASHBOARD_DATA[u]?.monthly_detail?.find(r => String(r.Month).slice(0,7) === monthStr);
    return r && r.Bench != null ? +(r.Bench * 100).toFixed(2) : null;
  };
  const fmtPct = (x) => x !== null ? (x >= 0 ? '+' : '') + x + '%' : 'N/A';
  const n50Val  = benchOf('nifty50');
  const n500Val = benchOf('nifty500');

  const bodyEl = document.getElementById('modal-body');
  const layers7 = Object.keys(LAYERS).filter(l => !isBenchKey(l));
  // The per-layer delta below compares against the ACTIVE universe's benchmark
  const vsLabel = state.universe === 'nifty50' ? 'vs Nifty 50'
                : state.universe === 'nifty500' ? 'vs Nifty 500'
                : 'vs Nifty 500';

  // Portfolio held during this month. Past months come from holdings.js snapshots;
  // the current/live month has no snapshot yet, so fall back to current_portfolio.
  const smap = DASHBOARD_DATA.sector_map || {};
  let holds = H()[monthStr] || [];
  let portoLabel = 'SQE Portfolio';
  if (!holds.length) {
    const cp = (d.current_portfolio || []).filter(s => s.clean_symbol && s.clean_symbol !== 'Stock');
    if (cp.length && isLive) {
      holds = cp.map(s => ({
        s: s.clean_symbol,
        sec: s.sector,
        w: s.weight != null ? +(s.weight * 100).toFixed(2) : null,
        p: s.ltp != null ? +(+s.ltp).toFixed(2) : null,
        r: s.mtd_change_pct != null ? +(+s.mtd_change_pct).toFixed(2) : null
      }));
      portoLabel = 'Live Portfolio';
    }
  }
  // A past month's Return is that month's own return (next month's formation
  // price / this month's - 1), never the current price. The latest snapshot
  // month has no following snapshot, so recover ITS end-of-month price from the
  // live portfolio: ltp / (1 + MTD%) ~= start of next month ~= end of this
  // month. That keeps the figure bounded to the month (not a current-price move).
  const snapMonths = Object.keys(H()).sort();
  const lastSnap = snapMonths.length ? snapMonths[snapMonths.length - 1] : null;
  if (holds.length && monthStr === lastSnap) {
    const liveBy = {};
    (d.current_portfolio || []).forEach(s => { if (s.clean_symbol) liveBy[s.clean_symbol] = s; });
    holds.forEach(h => {
      const s = liveBy[h.s];
      if (h.r == null && h.p && s && s.ltp != null && s.mtd_change_pct != null) {
        const endPx = s.ltp / (1 + s.mtd_change_pct / 100);
        if (endPx > 0) h.r = +((endPx / h.p - 1) * 100).toFixed(2);
      }
    });
  }

  // Reconcile contributions to the portfolio's month return. Stocks sold the
  // next month have no measurable return, but their COMBINED contribution is
  // known exactly (= month return - sum of the measured contributions). Spread
  // that residual across them by weight so the Contrib column sums to the
  // month's portfolio return. These filled values are marked estimated (~).
  const monthRet = (isLive || row.Base == null) ? null : +(row.Base * 100).toFixed(2);
  if (monthRet != null) {
    let known = 0, blankW = 0;
    holds.forEach(h => {
      if (h.w == null) return;
      if (h.r != null) known += h.w / 100 * h.r;
      else blankW += h.w;
    });
    if (blankW > 0.0001) {
      const implied = (monthRet - known) / (blankW / 100);
      holds.forEach(h => { if (h.r == null && h.w != null) { h.r = +implied.toFixed(2); h.est = true; } });
    } else {
      // Every holding has a measured return (e.g. the fully-rotated ML basket).
      // The per-holding detail and the monthly summary are built differently and
      // can diverge by a point or two, so shift each return by the same residual
      // (per weight) to keep the Contrib column summing to the month return.
      const totW = holds.reduce((a, h) => a + (h.w || 0), 0);
      const adj = totW > 0.0001 ? (monthRet - known) / (totW / 100) : 0;
      if (Math.abs(adj) > 0.005) holds.forEach(h => {
        if (h.r != null && h.w != null) { h.r = +(h.r + adj).toFixed(2); h.est = true; }
      });
    }
  }

  // Attach sector + expose for the investment calculator (recalcInvest)
  holds.forEach(h => { h.sec = h.sec || smap[h.s] || '—'; });
  window.__invHolds = holds;

  const fmtINR = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  // Past months: the price is that month's formation/entry price (the buy price).
  // Live month: it is the current LTP, so label it accordingly.
  const isLivePort = portoLabel === 'Live Portfolio';
  const priceHdr = isLivePort ? 'LTP' : 'Avg Buy Price';
  const priceTitle = isLivePort
    ? 'Live last-traded price'
    : "Entry (formation) price for this month's portfolio — what it was bought at";
  const holdingsHtml = `
    <div style="margin-top:1.25rem">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.6rem">
        <div class="modal-metric">${portoLabel} — ${holds.length} Holding${holds.length === 1 ? '' : 's'}</div>
        ${holds.length ? `<div style="display:flex;align-items:center;gap:.5rem">
          <span class="modal-metric">Invest</span>
          <span class="mono" style="color:var(--slate)">₹</span>
          <input id="inv-amt" type="number" min="0" step="10000" value="100000" oninput="recalcInvest()"
            style="width:130px;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:.4rem;
                   color:var(--cyan);font-family:var(--mono);font-weight:700;padding:.35rem .5rem;font-size:.8rem">
        </div>` : ''}
      </div>
      ${holds.length ? `
      <div style="border:1px solid var(--border);border-radius:.5rem;overflow:hidden">
        <table class="data-table mini-table">
          <colgroup>
            <col style="width:4%"><col style="width:14%"><col style="width:17%"><col style="width:9%"><col style="width:10%"><col style="width:11%"><col style="width:12%"><col style="width:8%"><col style="width:15%">
          </colgroup>
          <thead><tr>
            <th>#</th><th>Stock</th><th>Sector</th><th>Weight</th><th title="That month's own return. Blank when the stock isn't held the following month, so there's no next price to measure it against.">Return</th><th title="Weight × that month's return = the stock's contribution to the portfolio's return. The column sums to the portfolio return.">Contrib</th><th title="${priceTitle}">${priceHdr}</th><th>Qty</th><th>Amount</th>
          </tr></thead>
          <tbody>
            ${holds.map((h, i) => { const contrib = (h.r != null && h.w != null) ? +(h.w / 100 * h.r).toFixed(2) : null; return `<tr>
              <td class="text-muted mono" style="font-size:.65rem">${i + 1}</td>
              <td class="mono" style="font-weight:700">${h.s}</td>
              <td class="text-muted" style="font-size:.68rem">${h.sec}</td>
              <td class="mono">${h.w != null ? h.w + '%' : '—'}</td>
              <td class="mono ${h.r == null ? 'text-muted' : (h.r >= 0 ? 'text-emerald' : 'text-rose')}"${h.est ? ' title="Estimated — stock left the portfolio next month; return inferred from the residual so contributions sum to the month return."' : ''}>${h.r != null ? (h.est ? '~' : '') + (h.r >= 0 ? '+' : '') + h.r + '%' : '—'}</td>
              <td class="mono ${contrib == null ? 'text-muted' : (contrib >= 0 ? 'text-emerald' : 'text-rose')}">${contrib != null ? (h.est ? '~' : '') + (contrib >= 0 ? '+' : '') + contrib + '%' : '—'}</td>
              <td class="mono">${h.p != null ? fmtINR(h.p) : '—'}</td>
              <td class="mono text-cyan" id="iq${i}" style="font-weight:700">—</td>
              <td class="mono text-emerald" id="ia${i}">—</td>
            </tr>`; }).join('')}
          </tbody>
          <tfoot>
            <tr style="border-top:1px solid var(--border)">
              <td colspan="5" class="text-muted" style="font-size:.68rem;text-align:right">Portfolio Return (month)</td>
              <td class="mono ${monthRet != null && monthRet >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight:700">${monthRet != null ? (monthRet >= 0 ? '+' : '') + monthRet + '%' : '—'}</td>
              <td colspan="3"></td>
            </tr>
            <tr style="border-top:1px solid var(--border)">
              <td colspan="8" class="text-muted" style="font-size:.68rem;text-align:right">Total Invested</td>
              <td class="mono text-emerald" id="inv-total" style="font-weight:700">—</td>
            </tr>
            <tr>
              <td colspan="8" class="text-muted" id="inv-cash-label" style="font-size:.68rem;text-align:right">Cash Left</td>
              <td class="mono" id="inv-cash" style="color:var(--slate)">—</td>
            </tr>
          </tfoot>
        </table>
      </div>` : `<div class="text-muted" style="font-size:.75rem">No holdings snapshot available for this month.</div>`}
    </div>`;

  bodyEl.innerHTML = `
    <div class="modal-row" style="background:rgba(34,211,238,0.05);border-radius:.5rem;padding:.75rem;grid-template-columns:repeat(4,1fr)">
      <div>
        <div class="modal-metric">Nifty 50</div>
        <div class="modal-val" style="color:#94a3b8">${fmtPct(n50Val)}</div>
      </div>
      <div>
        <div class="modal-metric">Nifty 500</div>
        <div class="modal-val" style="color:#94a3b8">${fmtPct(n500Val)}</div>
      </div>
      <div>
        <div class="modal-metric">Portfolio Beta</div>
        <div class="modal-val" style="color:#f59e0b">${row.Port_Beta != null ? row.Port_Beta.toFixed(2) : '—'}</div>
      </div>
      <div>
        <div class="modal-metric">Ex-Ante Sharpe</div>
        <div class="modal-val" style="color:#22d3ee">${row.Ex_Ante_Sharpe != null ? row.Ex_Ante_Sharpe.toFixed(2) : '—'}</div>
      </div>
    </div>
    <div style="margin-top:1rem">
      ${layers7.map(l => {
        const v = row[l] != null ? +(row[l]*100).toFixed(2) : null;
        const vs = benchVal != null && v != null ? +(v - benchVal).toFixed(2) : null;
        const col = v !== null ? (v >= 0 ? '#10b981' : '#f43f5e') : '#64748b';
        const vsCol = vs !== null ? (vs >= 0 ? '#10b981' : '#f43f5e') : '#64748b';
        return `<div class="modal-row">
          <div><div class="modal-metric"><span class="ltag ${LAYERS[l].cls}" style="font-size:.6rem">${LAYERS[l].label}</span></div></div>
          <div>
            <div class="modal-metric">Return</div>
            <div class="modal-val" style="color:${col}">${v !== null ? (v>=0?'+':'')+v+'%' : 'N/A'}</div>
          </div>
          <div>
            <div class="modal-metric">${vsLabel}</div>
            <div class="modal-val" style="color:${vsCol}">${vs !== null ? (vs>=0?'+':'')+vs+'%' : 'N/A'}</div>
          </div>
        </div>`;
      }).join('')}
    </div>
    ${holdingsHtml}`;

  document.getElementById('hmModal').classList.add('open');
  recalcInvest();   // populate Qty/Amount for the default ₹1,00,000
}

window.openHeatModal = openHeatModal;

/* Investment calculator: split the entered amount across holdings by weight,
   buy whole shares at each price, and show qty + cost per stock with totals. */
function recalcInvest() {
  const holds = window.__invHolds || [];
  const amtEl = document.getElementById('inv-amt');
  if (!amtEl) return;
  const total = Math.max(0, +amtEl.value || 0);
  const fmt = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  let invested = 0;
  holds.forEach((h, i) => {
    const qEl = document.getElementById('iq' + i);
    const aEl = document.getElementById('ia' + i);
    if (!qEl || !aEl) return;
    if (h.p && h.p > 0 && h.w != null) {
      // Buy a minimum of 1 share of every holding, even if the weighted
      // allocation alone wouldn't cover it (the total adjusts upward).
      const qty = Math.max(1, Math.floor((total * (h.w / 100)) / h.p));
      const cost = qty * h.p;
      invested += cost;
      qEl.textContent = qty.toLocaleString('en-IN');
      aEl.textContent = fmt(cost);
    } else {
      qEl.textContent = '—';
      aEl.textContent = '—';
    }
  });
  const cash = total - invested;
  const tEl = document.getElementById('inv-total');
  const cEl = document.getElementById('inv-cash');
  const clEl = document.getElementById('inv-cash-label');
  if (tEl) tEl.textContent = fmt(invested);
  if (clEl) clEl.textContent = cash < 0 ? 'Extra Needed (min 1 share each)' : 'Cash Left';
  if (cEl) {
    cEl.textContent = (cash < 0 ? '-' : '') + fmt(Math.abs(cash));
    cEl.style.color = cash < 0 ? 'var(--rose)' : 'var(--slate)';
  }
}
window.recalcInvest = recalcInvest;

/* ══════════════════════════════════════════════
   EQUITY CURVES
══════════════════════════════════════════════ */
function renderPerformance(d) {
  try {
    renderEquity(d);
    renderDrawdown(d);
    renderRollingSharpe(d);
    renderCorrelation(d);
    renderAttribution(d);
    renderCrisis(d);
    renderWhatIf(d);
  } catch (e) {
    console.error('[Performance Tab] Error:', e);
  }
}

function renderEquity(d) {
  const ec = d.equity_curves;
  const datasets = Object.keys(LAYERS).map(l => ({
    label: LAYERS[l].label, data: ec[l] || [],
    borderColor: LAYERS[l].color, borderWidth: isBenchKey(l) ? 1.5 : 2.5,
    borderDash: isBenchKey(l) ? [6,4] : [],
    pointRadius: 0, tension: 0.3, fill: false
  }));

  mkChart('equityMain', 'line', {
    labels: ec.months,
    datasets: datasets
  }, { plugins: { legend: { position: 'top' } },
       scales: { y: { callback: v => '₹' + v.toFixed(2) } } 
  });
}

function renderDrawdown(d) {
  const ec = d.equity_curves;
  const labels = ec.months;
  
  const datasets = Object.keys(LAYERS).map(l => {
    const vals = ec[l] || [];
    let max = -Infinity;
    const dd = vals.map(v => {
      if (v > max) max = v;
      return max === 0 ? 0 : -((max - v) / max * 100);
    });
    return {
      label: LAYERS[l].label, data: dd,
      borderColor: LAYERS[l].color, borderWidth: 1.5,
      fill: true, backgroundColor: LAYERS[l].color + '11',
      pointRadius: 0, tension: 0.2
    };
  });

  mkChart('drawdownChart', 'line', { labels, datasets }, {
    plugins: { legend: { display: false } },
    scales: { y: { ticks: { callback: v => v.toFixed(1) + '%' } } }
  });
}

function renderRollingSharpe(d) {
  // Ex-Ante Sharpe Ratio per month (from monthly_detail)
  const md = (d.monthly_detail || []).filter(r =>
    /^\d{4}-\d{2}/.test(String(r.Month)) &&
    typeof r.Ex_Ante_Sharpe === 'number' && isFinite(r.Ex_Ante_Sharpe));
  if (!md.length) return;
  const labels = md.map(r => String(r.Month).slice(0, 7));

  mkChart('rollingSharpeChart', 'line', {
    labels,
    datasets: [{
      label: 'Ex-Ante Sharpe',
      data: md.map(r => +(+r.Ex_Ante_Sharpe).toFixed(2)),
      borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.10)',
      borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true
    }]
  }, { plugins: { legend: { display: false } } });
}

function renderCorrelation(d) {
  const stockCorr = d.stock_correlation;
  console.log('[Correlation] Data:', stockCorr);
  const container = document.getElementById('correlation-container');
  if (!container || !stockCorr || !stockCorr.symbols || stockCorr.symbols.length === 0) {
    if (container) container.innerHTML = '<div class="crisis-card" style="text-align:center">No stock correlation data available.</div>';
    return;
  }

  const { symbols, matrix } = stockCorr;
  const n = symbols.length;

  // Update card title to reflect Stock Correlation
  const titleEl = container.closest('.glass-card')?.querySelector('.card-title');
  if (titleEl) titleEl.textContent = 'Current Portfolio Stock Correlation';

  let html = `<div class="corr-grid-wrap">
    <div class="corr-grid" style="display:grid; grid-template-columns: 60px repeat(${n}, 1fr); gap:1px; background:var(--border); border:1px solid var(--border)">`;
  
  // Header row
  html += '<div class="corr-corner" style="background:var(--bg-2)"></div>';
  symbols.forEach(s => {
    html += `<div class="corr-label-v" style="background:var(--bg-2); font-size:0.6rem; padding:4px; text-align:center; font-weight:700" title="${s}">${s}</div>`;
  });
  
  // Data rows
  matrix.forEach((row, i) => {
    html += `<div class="corr-label-h" style="background:var(--bg-2); font-size:0.6rem; padding:4px; font-weight:700; border-right:1px solid var(--border)">${symbols[i]}</div>`;
    row.forEach((val, j) => {
      const alpha = Math.abs(val);
      const bg = val > 0 ? `rgba(16,185,129,${alpha})` : `rgba(244,63,94,${alpha})`;
      const color = alpha > 0.4 ? '#fff' : 'var(--text-1)';
      html += `<div class="corr-cell" style="background:${bg}; color:${color}; font-family:var(--font-mono); font-size:0.55rem; display:flex; align-items:center; justify-content:center; min-height:24px" title="${symbols[i]} vs ${symbols[j]}: ${val}">${val.toFixed(2)}</div>`;
    });
  });
  
  html += '</div></div>';
  container.innerHTML = html;
}


function renderAttribution(d) {
  const history = d.exec_history || [];
  const winners = [...history].filter(t => t.return > 0).sort((a,b) => b.return - a.return).slice(0, 5);
  const losers  = [...history].filter(t => t.return < 0).sort((a,b) => a.return - b.return).slice(0, 5);

  const container = document.getElementById('attribution-container');
  if (!container) return;

  const renderList = (list, title, color) => `
    <div style="flex:1">
      <h4 style="font-size:0.7rem; color:var(--muted); margin-bottom:0.5rem">${title}</h4>
      ${list.map(t => `
        <div class="attr-row">
          <span class="mono" style="font-weight:700">${t.symbol.split('_')[0]}</span>
          <span class="mono ${color}">${(t.return*100).toFixed(1)}%</span>
        </div>
      `).join('')}
    </div>
  `;

  container.innerHTML = `<div style="display:flex; gap:2rem">
    ${renderList(winners, 'TOP WINNERS', 'text-emerald')}
    ${renderList(losers, 'TOP DETRACTORS', 'text-rose')}
  </div>`;
}

function renderCrisis(d) {
  const events = [
    { name: 'Tech Sell-off', date: '2022-01' },
    { name: 'Adani Crisis',  date: '2023-01' },
    { name: 'General Election', date: '2024-06' }
  ];
  const container = document.getElementById('crisis-container');
  if (!container) return;

  const md = d.monthly_detail;
  const layers = Object.keys(LAYERS).filter(l => !isBenchKey(l));

  // Only show events that have data in the monthly detail
  const activeEvents = events.filter(e => md.some(r => r.Month.startsWith(e.date)));

  if (activeEvents.length === 0) {
    container.innerHTML = `<div class="crisis-card" style="text-align:center; color:var(--slate)">No historical crisis events found in the current backtest window.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="crisis-grid">
      ${activeEvents.map(e => {
        const row = md.find(r => r.Month.startsWith(e.date));
        if (!row) return `<div class="crisis-card">Data missing for ${e.name}</div>`;
        
        const benchRet = (row.Bench || 0) * 100;
        
        return `
          <div class="crisis-card">
            <div class="crisis-name">${e.name} (${e.date})</div>
            <div class="crisis-meta" style="margin-bottom:1rem">Benchmark: <b class="text-rose">${benchRet.toFixed(1)}%</b></div>
            
            <div style="display:flex; flex-direction:column; gap:0.4rem">
              <div style="display:flex; justify-content:space-between; font-size:0.6rem; color:var(--slate); padding-bottom:2px; border-bottom:1px solid var(--border)">
                <span>LAYER</span>
                <span>RETURN | PROTECTION</span>
              </div>
              ${layers.map(l => {
                const lRet = (row[l] || 0) * 100;
                const prot = lRet - benchRet;
                return `
                  <div class="mono" style="font-size:0.7rem; display:flex; justify-content:space-between; align-items:center">
                    <span class="ltag ${LAYERS[l].cls}" style="font-size:0.55rem">${LAYERS[l].label}</span>
                    <span>
                      <span class="${lRet >= 0 ? 'text-emerald' : 'text-rose'}">${lRet >= 0 ? '+' : ''}${lRet.toFixed(1)}%</span>
                      <span class="text-cyan" style="margin-left:0.5rem; font-weight:700">(${prot >= 0 ? '+' : ''}${prot.toFixed(1)}%)</span>
                    </span>
                  </div>
                `;
              }).join('')}
            </div>
            
            <div class="crisis-stat" style="margin-top:1.25rem; background:rgba(34,211,238,0.05); padding:0.5rem; border-radius:0.4rem; text-align:center">
              <span style="font-size:0.65rem; color:var(--cyan); font-weight:700">SHIELD EFFICACY:</span>
              <span class="text-emerald" style="font-size:0.8rem; font-weight:800; margin-left:0.5rem">
                +${(Math.max(...layers.map(l => (row[l]||0)*100 - benchRet))).toFixed(1)}% Max Defense
              </span>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function updateWhatIf(shock) {
  const d = D();
  const md = d.monthly_detail;
  const layers = Object.keys(LAYERS).filter(l => !isBenchKey(l));
  
  document.getElementById('whatif-shock-val').textContent = (shock > 0 ? '+' : '') + shock + '%';
  
  const resultsEl = document.getElementById('whatif-results');
  if (!resultsEl) return;

  const benchRets = md.map(r => r.Bench || 0);
  
  const breakdown = layers.map(l => {
    const layerRets = md.map(r => r[l] || 0);
    const beta = calculateBeta(layerRets, benchRets);
    const impact = shock * beta;
    return {
      id: l,
      label: LAYERS[l].label,
      beta: beta,
      impact: impact,
      vsBench: impact - shock
    };
  });

  resultsEl.innerHTML = `
    <table class="data-table" style="margin-top:1rem; font-size:0.75rem">
      <thead>
        <tr>
          <th>Strategy Layer</th>
          <th>Est. Beta</th>
          <th>Proj. Impact</th>
          <th>Alpha vs Bench</th>
        </tr>
      </thead>
      <tbody>
        ${breakdown.map(b => `
          <tr>
            <td><span class="ltag ${LAYERS[b.id].cls}" style="font-size:0.6rem">${b.label}</span></td>
            <td class="mono">${b.beta.toFixed(2)}</td>
            <td class="mono ${b.impact >= 0 ? 'text-emerald' : 'text-rose'}" style="font-weight:700">${(b.impact >= 0 ? '+' : '') + b.impact.toFixed(2)}%</td>
            <td class="mono ${b.vsBench >= 0 ? 'text-emerald' : 'text-rose'}">${(b.vsBench >= 0 ? '+' : '') + b.vsBench.toFixed(2)}%</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;

  // Update main summary cards
  const portBeta = breakdown.find(b => b.id === 'Base')?.beta || 1.0;
  const portImpact = shock * portBeta;
  const impactEl = document.getElementById('whatif-impact');
  impactEl.textContent = (portImpact >= 0 ? '+' : '') + portImpact.toFixed(2) + '%';
  impactEl.className = 'mono ' + (portImpact >= 0 ? 'text-emerald' : 'text-rose');

  const hedgeProt = shock < 0 ? Math.abs((shock * 1.0) - (shock * 0.6)) : 0; // Simulated hedge efficacy
  document.getElementById('whatif-hedge').textContent = (hedgeProt > 0 ? '+' : '') + hedgeProt.toFixed(2) + '%';
}

function calculateBeta(layer, bench) {
  const n = layer.length;
  if (n < 2) return 1.0;
  const muB = bench.reduce((a,b)=>a+b,0)/n;
  const varB = bench.reduce((a,b)=>a+Math.pow(b-muB,2),0)/n;
  const covLB = layer.reduce((acc,li,i) => acc + (li-(layer.reduce((a,b)=>a+b,0)/n))*(bench[i]-muB), 0)/n;
  return varB === 0 ? 0 : covLB / varB;
}

function renderWhatIf(d) {
  const container = document.getElementById('whatif-container');
  if (!container) return;

  container.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:1.5rem">
      <div>
        <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem">
          <label class="mono" style="font-size:0.8rem; color:var(--muted)">Benchmark Shock Simulator</label>
          <span id="whatif-shock-val" class="mono text-cyan" style="font-weight:700">0%</span>
        </div>
        <input type="range" id="whatif-slider" min="-50" max="50" value="0" step="1" 
               style="width:100%; height:8px; border-radius:4px; background:var(--bg-2); cursor:pointer"
               oninput="updateWhatIf(this.value)">
      </div>
      
      <div class="grid-2">
        <div class="crisis-card" style="border-left:4px solid var(--rose)">
          <div class="crisis-name" style="font-size:0.7rem; color:var(--muted)">CORE MODEL IMPACT</div>
          <div id="whatif-impact" class="mono" style="font-size:1.5rem; font-weight:700; margin:0.5rem 0">0.00%</div>
          <div style="font-size:0.75rem; color:var(--slate)">Projected move for SQE layer</div>
        </div>
        <div class="crisis-card" style="border-left:4px solid var(--emerald)">
          <div class="crisis-name" style="font-size:0.7rem; color:var(--muted)">HEDGE PROTECTION ESTIMATE</div>
          <div id="whatif-hedge" class="mono text-emerald" style="font-size:1.5rem; font-weight:700; margin:0.5rem 0">0.00%</div>
          <div style="font-size:0.75rem; color:var(--slate)">Estimated loss prevention via Defense layers</div>
        </div>
      </div>

      <div id="whatif-results"></div>
    </div>
  `;
  updateWhatIf(0);
}

window.updateWhatIf = updateWhatIf;

function renderRegimeBadge(d) {
  const badge = document.getElementById('regime-badge');
  if (!badge) return;
  
  const base = d.layer_metrics.Base;
  const alpha = base.Alpha || 0;
  
  let label = 'Neutral';
  let cls = 'neutral';
  
  if (alpha > 5) { label = 'Bullish Mode'; cls = 'bull'; }
  else if (alpha > 0) { label = 'Positive Bias'; cls = 'bias'; }
  else if (alpha < -5) { label = 'Defense Mode'; cls = 'bear'; }
  
  badge.innerHTML = `<span class="regime-dot ${cls}"></span> ${label}`;
  badge.className = `regime-badge ${cls}`;
}

function exportReport() {
  window.print();
}

window.exportReport = exportReport;

/* ══════════════════════════════════════════════
   LAYER METRICS
══════════════════════════════════════════════ */
function renderLayers(d) {
  const layers = Object.keys(LAYERS); // includes 'Bench'

  // Table
  // Ex-Ante Sharpe from exec_summary
  const exAnte = d.exec_summary?.['Avg Ex-Ante Sharpe'] || {};
  document.getElementById('layerTableBody').innerHTML = layers.map(l => {
    const m = d.layer_metrics[l];
    if (!m) return '';
    const ea = exAnte[l] != null ? exAnte[l].toFixed(2) : '—';
    const isBench = isBenchKey(l);
    
    // For Benchmark, Alpha is not applicable (it is the benchmark itself)
    const alphaVal = isBench ? '—' : (m.Alpha >= 0 ? '+' : '') + m.Alpha.toFixed(2) + '%';
    const alphaClass = isBench ? 'text-muted' : (m.Alpha >= 0 ? 'text-emerald' : 'text-rose');
    
    return `<tr>
      <td><span class="ltag ${LAYERS[l].cls}">${LAYERS[l].label}</span></td>
      <td class="mono ${m.CAGR>=0?'text-emerald':'text-rose'}" style="font-weight:700">${m.CAGR.toFixed(2)}%</td>
      <td class="mono">${ea}</td>
      <td class="mono">${m.Calmar.toFixed(2)}</td>
      <td class="mono text-rose" style="font-weight:700">${m.Max_DD.toFixed(2)}%</td>
      <td class="mono">${m.Win_Rate.toFixed(1)}%</td>
      <td class="mono text-emerald">${m.Avg_Gain.toFixed(2)}%</td>
      <td class="mono text-rose">${m.Avg_Loss.toFixed(2)}%</td>
      <td class="mono text-emerald" style="font-weight:700">${m.Total_Return.toFixed(2)}%</td>
      <td class="mono ${alphaClass}" style="${!isBench ? 'font-weight:700' : ''}">${alphaVal}</td>
    </tr>`;
  }).join('');

  // Radar chart
  mkChart('radarChart', 'radar', {
    labels: ['CAGR','Sharpe','Sortino','Win Rate','Alpha'],
    datasets: layers.map(l => {
      const m = d.layer_metrics[l];
      if (!m) return null;
      const isBench = isBenchKey(l);
      return {
        label: LAYERS[l].label,
        data: [m.CAGR/30*100, m.Sharpe/2*100, m.Sortino/3*100, m.Win_Rate, Math.max(0,m.Alpha/20*100)],
        borderColor: LAYERS[l].color,
        backgroundColor: LAYERS[l].color + '18',
        pointRadius: isBench ? 0 : 3,
        borderWidth: isBench ? 1.5 : 2,
        borderDash: isBench ? [5, 4] : []
      };
    }).filter(Boolean)
  }, { scales: { r: { grid:{color:'rgba(255,255,255,0.08)'}, ticks:{display:false},
                       pointLabels:{color:'#94a3b8',font:{size:10}} } },
       plugins: { legend:{position:'bottom',labels:{color:'#94a3b8',boxWidth:8,font:{size:9}}} } });

  // Executive summary table
  renderExecTable(d);
}

function renderExecTable(d) {
  const el = document.getElementById('execTable');
  if (!el) return;
  const summary = d.exec_summary;
  const stratLayers = ['Base'];
  const metrics = Object.keys(summary).filter(m => m !== 'Sharpe' && m !== 'Sortino');

  // Strategy columns come from the active universe; the benchmark columns always
  // show BOTH Nifty 50 and Nifty 500 so the strategy can be read against each index.
  const n50  = DASHBOARD_DATA.nifty50?.exec_summary;
  const n500 = DASHBOARD_DATA.nifty500?.exec_summary;
  const columns = [
    ...stratLayers.map(l => ({ label: LAYERS[l].label, cls: LAYERS[l].cls,
                               isBench: false, get: m => summary[m]?.[l] })),
    { label: 'Nifty 50',  cls: 'ltag-bench', isBench: true, get: m => n50?.[m]?.Bench },
    { label: 'Nifty 500', cls: 'ltag-bench', isBench: true, get: m => n500?.[m]?.Bench },
  ];

  const pctMetrics = ['CAGR','XIRR','Volatility','Alpha vs Bench','Max Drawdown',
                      'VaR 95%','VaR 99%','CVaR 95%','CVaR 99%','Downside Dev',
                      'Best Month','Worst Month','Avg Gain','Avg Loss',
                      'Rolling 1Y','Rolling 3Y','Abs Return'];

  el.innerHTML = `
    <thead>
      <tr>
        <th>Metric</th>
        ${columns.map(c => `<th><span class="ltag ${c.cls}" style="font-size:.6rem">${c.label}</span></th>`).join('')}
      </tr>
    </thead>
    <tbody>
      ${metrics.map(metric => `
        <tr>
          <td class="text-muted" style="font-size:.72rem;font-weight:600">${metric}</td>
          ${columns.map(c => {
            const v = c.get(metric);
            if (v == null) return '<td class="mono text-muted" style="font-size:.75rem">—</td>';

            // Some metrics are not applicable to a benchmark column
            if (c.isBench && (metric === 'Alpha vs Bench' || metric === 'Avg Ex-Ante Sharpe' || metric === 'Info Ratio')) {
              return '<td class="mono text-muted" style="font-size:.75rem">—</td>';
            }

            const pct = pctMetrics.includes(metric);
            const display = pct ? (v*100).toFixed(2)+'%' : v.toFixed(4);
            const col = c.isBench && metric === 'Alpha vs Bench' ? 'text-muted' : (v >= 0 ? 'text-emerald' : 'text-rose');
            return `<td class="mono ${col}" style="font-size:.75rem">${display}</td>`;
          }).join('')}
        </tr>`).join('')}
    </tbody>`;
}

/* ══════════════════════════════════════════════
   CHURNING
══════════════════════════════════════════════ */
function renderChurning(d) {
  const rawChurn = d.churning_data || [];
  // Strict filter: Month must be a string like "2021-04" (YYYY-MM)
  const monthRegex = /^\d{4}-\d{2}$/;
  const blacklist = ['ULTRA', 'COMBO', 'EMA', 'ST', 'BASE', 'SUMMARY', 'AVG', 'LAYER', 'STOCK'];
  
  const churn = rawChurn.filter(r => {
    const m = String(r.Month || '').trim().toUpperCase();
    if (!m || m === '0.0' || m === '0') return false;
    // If it contains any blacklist word, reject it
    if (blacklist.some(word => m.includes(word))) return false;
    // Must also match the date pattern
    return monthRegex.test(String(r.Month).trim());
  });
  
  console.log(`[Churning] Filtered ${rawChurn.length} down to ${churn.length} valid months.`);
  console.table(churn.slice(0, 5)); // Log first 5 rows to console for verification
  
  const sorted = [...churn].sort((a,b) => a.Month > b.Month ? 1 : -1);

  // Calculate Churning Statistics
  const avgAdd = churn.length ? churn.reduce((a, b) => a + (b['Base Add'] || 0), 0) / churn.length : 0;
  const avgRem = churn.length ? churn.reduce((a, b) => a + (b['Base Rem'] || 0), 0) / churn.length : 0;
  const maxAdd = churn.length ? Math.max(...churn.map(r => r['Base Add'] || 0)) : 0;
  const maxRem = churn.length ? Math.max(...churn.map(r => r['Base Rem'] || 0)) : 0;

  const kpiEl = document.getElementById('churnKpis');
  if (kpiEl) {
    kpiEl.innerHTML = [
      { label: 'Avg Add (Base)', val: avgAdd, color: 'emerald' },
      { label: 'Avg Rem (Base)', val: avgRem, color: 'rose' },
      { label: 'Max Add',        val: maxAdd, color: 'cyan' },
      { label: 'Max Rem',        val: maxRem, color: 'gold' }
    ].map(k => `
      <div class="kpi-card" style="--accent: var(--${k.color})">
        <span class="kpi-label">${k.label}</span>
        <span class="kpi-value text-${k.color}">${k.val.toFixed(2)}</span>
      </div>`).join('');
  }

  document.getElementById('churningBody').innerHTML = [...sorted].reverse().map(r => `
    <tr>
      <td class="mono">${r.Month}</td>
      <td class="mono">${r.Stock_Count ?? '—'}</td>
      <td class="text-emerald mono">${r['Base Add'] ?? '—'}</td>
      <td class="text-rose mono">${r['Base Rem'] ?? '—'}</td>
    </tr>`).join('');

  const churnKeys = ['Base'];
  mkChart('churnAddChart', 'line', {
    labels: sorted.map(r => r.Month),
    datasets: churnKeys.map((k,i) => ({
      label: k + ' Add', data: sorted.map(r => r[k + ' Add'] ?? 0),
      borderColor: LAYERS[k].color,
      borderWidth: 2, pointRadius: 2, tension: 0.3, fill: false
    }))
  }, {});

  mkChart('churnRemChart', 'line', {
    labels: sorted.map(r => r.Month),
    datasets: churnKeys.map((k,i) => ({
      label: k + ' Rem', data: sorted.map(r => r[k + ' Rem'] ?? 0),
      borderColor: LAYERS[k].color,
      borderWidth: 2, pointRadius: 2, tension: 0.3, fill: false
    }))
  }, {});
}

/* ══════════════════════════════════════════════
   PORTFOLIO
══════════════════════════════════════════════ */
function renderPortfolio(d) {
  const port = d.current_portfolio || [];
  const last = d.monthly_detail[d.monthly_detail.length - 1] || {};
  const lp   = d.live_performance || {};

  // ── Row 1: Portfolio/Benchmark KPIs ──────────
  document.getElementById('portKpis').innerHTML = [
    { label:'Holdings',      val:port.length,          color:'#22d3ee', accent:'#22d3ee' },
    { label:'Portfolio Beta',val:+(last.Port_Beta||0).toFixed(2), color:'#f59e0b', accent:'#f59e0b' },
    { label:'Stock Count',   val:+(last.Stock_Count||0), color:'#10b981', accent:'#10b981' }
  ].map(k => `
    <div class="kpi-card" style="--accent:${k.accent}">
      <span class="kpi-label">${k.label}</span>
      <span class="kpi-value" style="color:${k.color}">${typeof k.val==='number'?k.val.toFixed(2):k.val}</span>
    </div>`).join('');

  // ── Row 2: Live Performance + MTD ────────────
  const portRet  = lp.portfolio_ret  || 0;
  const benchRet = lp.benchmark_ret  || 0;
  const alpha    = lp.alpha          || 0;
  const portMtd  = lp.portfolio_mtd  || 0;
  const benchMtd = lp.benchmark_mtd  || 0;
  const alphaMtd = lp.alpha_mtd      || 0;

  const arrow = (v) => v >= 0 ? '▲' : '▼';
  const sign  = (v) => v >= 0 ? '+' : '';
  const col   = (v) => v >= 0 ? '#10b981' : '#f43f5e';

  document.getElementById('portPerformanceKpis').innerHTML = [
    { label:'Portfolio Today', val:portRet,  extra: arrow(portRet),  color: col(portRet),  accent:'#10b981' },
    { label:'Benchmark Today', val:benchRet, extra: arrow(benchRet), color: col(benchRet), accent:'#94a3b8' },
    { label:'Daily Alpha',     val:alpha,    extra:'α',               color: col(alpha),    accent:'#22d3ee' },
    { label:'Portfolio MTD',   val:portMtd,  extra: arrow(portMtd),  color: col(portMtd),  accent:'#10b981' },
    { label:'Benchmark MTD',   val:benchMtd, extra: arrow(benchMtd), color: col(benchMtd), accent:'#94a3b8' },
    { label:'MTD Alpha',       val:alphaMtd, extra:'α',               color: col(alphaMtd), accent:'#22d3ee' },
  ].map(k => `
    <div class="kpi-card" style="--accent:${k.accent}">
      <div style="display:flex;justify-content:space-between;align-items:center;width:100%">
        <span class="kpi-label">${k.label}</span>
        <span style="font-size:0.75rem;color:${k.color};font-weight:700">${k.extra}</span>
      </div>
      <span class="kpi-value" style="color:${k.color}">${sign(k.val)}${k.val.toFixed(2)}%</span>
    </div>`).join('');

  // ── Holdings table + investment calculator ─────────────
  const cleanPort = port.filter(s => s.clean_symbol && s.clean_symbol !== 'Stock');

  window.__portHolds = cleanPort.map(s => ({
    s: s.clean_symbol,
    sec: s.sector,
    w: s.weight != null ? +(s.weight * 100).toFixed(2) : null,
    p: (s.ltp != null && s.ltp > 0) ? +(+s.ltp).toFixed(2) : null,
    chg: s.change_pct
  }));

  document.getElementById('holdingsBody').innerHTML = window.__portHolds.map((h,i) => {
    const chg = h.chg || 0;
    const chgCol = chg >= 0 ? 'text-emerald' : 'text-rose';
    return `<tr>
      <td class="text-muted mono" style="font-size:.7rem">${i+1}</td>
      <td class="mono" style="font-weight:700">${h.s}</td>
      <td class="text-muted" style="font-size:.7rem">${h.sec}</td>
      <td class="mono">${h.w != null ? h.w + '%' : '—'}</td>
      <td class="mono">${h.p != null ? '₹'+h.p.toLocaleString('en-IN') : '—'}</td>
      <td class="mono ${chgCol}" style="font-weight:700">${h.p != null ? (chg>=0?'+':'')+(+chg).toFixed(2)+'%' : '—'}</td>
      <td class="mono text-cyan" id="piq${i}" style="font-weight:700">—</td>
      <td class="mono text-emerald" id="pia${i}">—</td>
    </tr>`;
  }).join('');

  const pa = document.getElementById('pinv-amt');
  if (pa) pa.value = sharedInvestAmount;   // reflect the shared amount
  recalcPortInvest();
  renderSectorPie('portSector', cleanPort);
}

/* Investment calculator for the Live Portfolio tab (same math as the heatmap
   modal's recalcInvest, with its own 'p'-prefixed element ids). */
function recalcPortInvest() {
  const holds = window.__portHolds || [];
  const amtEl = document.getElementById('pinv-amt');
  if (!amtEl) return;
  const total = Math.max(0, +amtEl.value || 0);
  sharedInvestAmount = total;   // keep the Portfolio Changes tab in sync
  const fmt = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  let invested = 0;
  holds.forEach((h, i) => {
    const qEl = document.getElementById('piq' + i);
    const aEl = document.getElementById('pia' + i);
    if (!qEl || !aEl) return;
    if (h.p && h.p > 0 && h.w != null) {
      const qty = Math.max(1, Math.floor((total * (h.w / 100)) / h.p));
      const cost = qty * h.p;
      invested += cost;
      qEl.textContent = qty.toLocaleString('en-IN');
      aEl.textContent = fmt(cost);
    } else {
      qEl.textContent = '—';
      aEl.textContent = '—';
    }
  });
  const cash = total - invested;
  const tEl = document.getElementById('pinv-total');
  const cEl = document.getElementById('pinv-cash');
  const clEl = document.getElementById('pinv-cash-label');
  if (tEl) tEl.textContent = fmt(invested);
  if (clEl) clEl.textContent = cash < 0 ? 'Extra Needed (min 1 share each)' : 'Cash Left';
  if (cEl) {
    cEl.textContent = (cash < 0 ? '-' : '') + fmt(Math.abs(cash));
    cEl.style.color = cash < 0 ? 'var(--rose)' : 'var(--slate)';
  }
}
window.recalcPortInvest = recalcPortInvest;

/* ══════════════════════════════════════════════
   TRADES
══════════════════════════════════════════════ */
function renderTrades(d) {
  // Portfolio Changes view: every current holding vs last month's portfolio.
  // Previous weight/price come from the most recent snapshot before this month,
  // so the "Change" can be computed at the user's chosen investment amount.
  const port = (d.current_portfolio || []).filter(s => s.clean_symbol && s.clean_symbol !== 'Stock');
  const snap = H();
  const liveMonth = String((port.find(s => s.date) || {}).date || DASHBOARD_DATA.last_update || '').slice(0, 7);
  const prevMonths = Object.keys(snap).sort().filter(m => !liveMonth || m < liveMonth);
  const prevHolds = prevMonths.length ? snap[prevMonths[prevMonths.length - 1]] : [];
  const prevBy = {};
  prevHolds.forEach(x => { prevBy[x.s] = x; });

  window.__chgHolds = port.map(s => {
    const prev = prevBy[s.clean_symbol];
    return {
      s: s.clean_symbol,
      sec: s.sector || '—',
      w: s.weight != null ? +(s.weight * 100).toFixed(2) : null,
      p: (s.ltp != null && s.ltp > 0) ? +(+s.ltp).toFixed(2) : null,
      prevW: prev ? prev.w : null,
      prevP: (prev && prev.p > 0) ? prev.p : null,
      isNew: !prev
    };
  });

  const ca = document.getElementById('cinv-amt');
  if (ca) ca.value = sharedInvestAmount;   // reflect the shared amount
  recalcChangesInvest();
}

/* Portfolio Changes calculator. The Change column is the share adjustment the
   USER would make to rebalance from last month's portfolio to the current one
   at the chosen Invest amount: current qty - previous qty (both whole shares,
   min 1). The indicator (🔥 new / ▲ up / ▼ down / ↔ same) follows that delta,
   so it updates live as the amount changes. Shares sharedInvestAmount with the
   Live Portfolio tab. */
function recalcChangesInvest() {
  const holds = window.__chgHolds || [];
  const amtEl = document.getElementById('cinv-amt');
  if (!amtEl) return;
  const total = Math.max(0, +amtEl.value || 0);
  sharedInvestAmount = total;   // keep the Live Portfolio tab in sync
  const fmt = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  const qtyAt = (w, p) => (p > 0 && w != null) ? Math.max(1, Math.floor((total * (w / 100)) / p)) : null;

  holds.forEach(h => {
    h.curQty = qtyAt(h.w, h.p);
    h.cost = h.curQty != null ? h.curQty * h.p : 0;
    if (h.isNew || h.prevW == null || h.prevP == null) {
      h.change = h.curQty;   // a brand-new position: buy the whole thing
      h.ind = { icon: '🔥', label: 'New', color: '#22d3ee', rank: 0 };
    } else {
      const prevQty = qtyAt(h.prevW, h.prevP) || 0;
      h.change = (h.curQty || 0) - prevQty;
      if (h.change > 0)      h.ind = { icon: '▲', label: 'Increased', color: '#10b981', rank: 1 };
      else if (h.change < 0) h.ind = { icon: '▼', label: 'Decreased', color: '#f43f5e', rank: 2 };
      else                   h.ind = { icon: '↔', label: 'No change', color: '#94a3b8', rank: 3 };
    }
  });
  holds.sort((a, b) => a.ind.rank - b.ind.rank || (b.w || 0) - (a.w || 0));

  let invested = 0;
  document.getElementById('tradesBody').innerHTML = holds.map(h => {
    if (h.curQty != null) invested += h.cost;
    const chg = h.change;
    const chgTxt = h.ind.rank === 0
      ? 'NEW +' + (chg || 0)
      : (chg > 0 ? '+' + chg : (chg < 0 ? String(chg) : '0'));
    return `<tr>
      <td title="${h.ind.label}" style="text-align:center;font-size:.9rem;color:${h.ind.color}">${h.ind.icon}</td>
      <td class="mono" style="font-weight:700">${h.s}</td>
      <td class="text-muted" style="font-size:.7rem">${h.sec}</td>
      <td class="mono" style="font-weight:700;color:${h.ind.color}">${chgTxt}</td>
      <td class="mono">${h.w != null ? h.w + '%' : '—'}</td>
      <td class="mono">${h.p != null ? '₹' + h.p.toLocaleString('en-IN') : '—'}</td>
      <td class="mono text-cyan" style="font-weight:700">${h.curQty != null ? h.curQty.toLocaleString('en-IN') : '—'}</td>
      <td class="mono text-emerald">${h.curQty != null ? fmt(h.cost) : '—'}</td>
    </tr>`;
  }).join('');

  const cash = total - invested;
  const tEl = document.getElementById('cinv-total');
  const cEl = document.getElementById('cinv-cash');
  const clEl = document.getElementById('cinv-cash-label');
  if (tEl) tEl.textContent = fmt(invested);
  if (clEl) clEl.textContent = cash < 0 ? 'Extra Needed (min 1 share each)' : 'Cash Left';
  if (cEl) {
    cEl.textContent = (cash < 0 ? '-' : '') + fmt(Math.abs(cash));
    cEl.style.color = cash < 0 ? 'var(--rose)' : 'var(--slate)';
  }
}
window.recalcChangesInvest = recalcChangesInvest;

/* ══════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════ */
function renderSectorPie(canvasId, port) {
  const counts = {};
  port.forEach(s => { counts[s.sector] = (counts[s.sector]||0) + 1; });
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const labelCol = isLight ? '#475569' : '#94a3b8';
  
  const COLORS = ['#22d3ee','#f59e0b','#10b981','#f43f5e','#8b5cf6','#06b6d4','#ec4899','#f97316'];
  mkChart(canvasId, 'doughnut', {
    labels: Object.keys(counts),
    datasets: [{ data: Object.values(counts), backgroundColor: COLORS, borderWidth: 0, hoverOffset: 12 }]
  }, { 
    cutout: '72%', 
    plugins: { 
      legend: { position: 'right', labels: { color: labelCol, boxWidth: 10, font: { size: 10, weight: '500' } } }
    }
  });
}

/* ══════════════════════════════════════════════
   INIT
══════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  const savedTheme = localStorage.getItem('som-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  
  Chart.defaults.color = savedTheme === 'light' ? '#475569' : '#94a3b8';
  Chart.defaults.font.family = "'Inter', sans-serif";

  const d = DASHBOARD_DATA;
  document.getElementById('last-refresh').textContent =
    'Terminal Updated: ' + (d.last_update || 'N/A');

  if (window.particlesJS) {
    particlesJS('particles-js', {
      particles: {
        number:{value:25,density:{enable:true,value_area:900}},
        color:{value:['#22d3ee','#f59e0b']},
        shape:{type:'circle'},
        opacity:{value:0.12,random:true},
        size:{value:1.5,random:true},
        line_linked:{enable:true,distance:160,color:'#22d3ee',opacity:0.06,width:1},
        move:{enable:true,speed:0.4,random:true,out_mode:'out'}
      },
      interactivity:{ events:{onhover:{enable:true,mode:'grab'}} },
      retina_detect:true
    });
  }

  renderTab('overview');
});
