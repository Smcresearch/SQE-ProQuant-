/* Live LTP overlay — polls ltp.json (written by feed_ltp.py on 10.10.5.33) and
   pushes live prices onto every universe's current_portfolio, then re-renders the
   live-relevant tabs. Degrades gracefully: if ltp.json is absent (e.g. the public
   GitHub Pages site), it just leaves the static last-run prices in place. */
(function () {
  var live = {};
  var UNIV = ['nifty50', 'nifty500', 'total759', 'ml_forecast', 'high_quality'];

  function apply() {
    if (typeof DASHBOARD_DATA === 'undefined') return;
    UNIV.forEach(function (u) {
      var cp = DASHBOARD_DATA[u] && DASHBOARD_DATA[u].current_portfolio;
      if (!cp) return;
      cp.forEach(function (s) {
        var p = live[s.clean_symbol];
        if (p != null && p > 0) s.ltp = p;
      });
    });
  }

  function badge(txt, ok) {
    var el = document.getElementById('live-ltp-badge');
    if (!el) {
      el = document.createElement('div');
      el.id = 'live-ltp-badge';
      el.style.cssText = 'position:fixed;bottom:10px;right:12px;z-index:9999;' +
        'font:600 11px Inter,system-ui,sans-serif;padding:5px 11px;border-radius:8px;' +
        'letter-spacing:.02em;backdrop-filter:blur(6px)';
      document.body.appendChild(el);
    }
    el.style.background = ok ? 'rgba(16,185,129,.14)' : 'rgba(148,163,184,.14)';
    el.style.color = ok ? '#10b981' : '#94a3b8';
    el.style.border = '1px solid ' + (ok ? 'rgba(16,185,129,.4)' : 'rgba(148,163,184,.3)');
    el.textContent = (ok ? '● LIVE  ' : '○  ') + txt;
  }

  function poll() {
    fetch('ltp.json?_=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) {
        live = j.ltp || {};
        apply();
        badge('LTP ' + String(j.updated || '').slice(11) + ' · ' + Object.keys(live).length + ' stocks', true);
        if (typeof state !== 'undefined' && typeof renderTab === 'function' &&
            ['portfolio', 'overview', 'trades'].indexOf(state.tab) >= 0) {
          renderTab(state.tab);
        }
      })
      .catch(function () { badge('feed offline (static prices)', false); });
  }

  setInterval(poll, 2000);
  if (document.readyState !== 'loading') poll();
  else document.addEventListener('DOMContentLoaded', poll);
})();
