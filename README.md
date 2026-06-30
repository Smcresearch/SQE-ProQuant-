# SQE — All Indices Portfolio Dashboard

Institutional-grade portfolio analytics for the Sharpe Efficient Portfolio
(SQE) hedge strategy, showing the **All Indices** universe.

This is a static dashboard (HTML / CSS / vanilla JS) intended for GitHub Pages.

## Files
- `index.html` — page shell and layout
- `style.css` — styling
- `app.js` — rendering logic and interactivity
- `data.js` — precomputed dashboard data (`DASHBOARD_DATA`)

## Local preview
Open `index.html` directly in a browser, or serve the folder:

```sh
python -m http.server 8000
# then visit http://localhost:8000
```

## Deploy (GitHub Pages)
Push to `main`, then in the repo settings enable **Pages → Deploy from branch → main / root**.

> Note: `index.html` loads `app.js`/`data.js` with a `?v=` cache-bust token.
> Bump it whenever `app.js` or `data.js` changes so browsers load the fresh files.
