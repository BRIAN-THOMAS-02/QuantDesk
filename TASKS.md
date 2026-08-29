# QuantDesk India — Task & Verification Tracker

> **Living document.** Updated after every change. Status legend:
> `DONE` · `IN-PROGRESS` · `BLOCKED` · `PENDING`
>
> **How to run** (see README "Quick Start"):
> ```bash
> source .venv/bin/activate
> python main.py serve # http://127.0.0.1:8080
> python -m pytest tests/ -q # 40 tests
> ```
>
> **Data reality check (important):** Today is **Saturday** → NSE markets are
> CLOSED. NSE's public endpoints (`/api/option-chain-*`, FII/DII, bulk deals)
> actively block/403 on weekends and on non-browser sessions. The only reliable
> weekend data source is **yfinance (OSINT)**, which serves last-close OHLCV +
> fundamentals at any time. NSE-dependent features are **expected to be empty on
> weekends** and should be re-verified on a trading day. Per the user, real
> broker/API keys (Zerodha Kite, etc.) will be supplied later — until then all
> trading stays in PAPER mode and NSE live paths must **degrade gracefully,
> never crash**.

---

## Summary

| Area | Status |
|------|--------|
| 40-unit test suite | All passing |
| Quant models (BS/CRR/MC/stochastic/vol/risk) | Verified w/ yfinance + synthetic data |
| yfinance CLI pipeline (quote/signal/backtest/optimize/bs/simulate/vol/formula) | Working |
| Web API smoke test | Working (yfinance paths) |
| NSE live paths (option chain / FII-DII / whales) | BLOCKED on weekend — degrades gracefully; re-verify on trading day |
| Backend bug fixes this session | 7 fixes (see below) |

---

## Backend Bug Fixes (this session)

| # | Bug | File:Line | Status |
|---|-----|-----------|--------|
| 1 | `atr_percentile`called `atr(high,low,close,window)`(4 args) but `analysis.indicators.atr(df, n=14)`takes a **DataFrame** — crashed `vol`CLI + /api/volatility. | `quant/volatility.py:79`| Fixed (builds DataFrame, passes `window`) |
| 2 | `capm_alpha_beta`did `beta_alpha, *_ = np.linalg.lstsq(...)[0]`→ split the 2-elem coeff vector into scalar+list → `IndexError: invalid index to scalar variable`. Surfaced by the F&O refactor. | `quant/fno_analytics.py:51`| Fixed (`beta_alpha = ...[0]`) |
| 3 | `option_chain`ran `dropna(subset=["strike"])`on an **empty** DataFrame (no `strike`col) → `KeyError: ['strike']`when NSE returned no rows. | `data/providers/nse_provider.py:122`| Fixed (column-guarded, returns empty typed frame) |
| 4 | `screener`returned `NaN`/`np.float64`→ FastAPI's strict JSON encoder raised. | `webapp/server.py`| Fixed (`json_safe`sanitizer applied to screener + F&O analytics) |
| 5 | `YFinanceProvider.quote`used `fast_info.lastPrice`which lazily fetches 1y history and raises `KeyError: 'currentTradingPeriod'`on the installed yfinance version. | `data/providers/yfinance_provider.py:33`| Fixed (try fast_info, fall back to history-derived snapshot) |
| 6 | `SupertrendRSI.generate`computed `adx`as a local Series but read `last.adx`→ `AttributeError: 'Series' has no attribute 'adx'`. | `strategies/swing.py:25`| Fixed (assign `df["adx"]`) |
| 7 | `PortfolioOptimizer.max_sharpe`/`min_variance`passed no symbol index to `_to_weights`→ weights keyed `"0","1",...`; `summary()`alignment then zeroed every weight → `exp_ret_pct: 0.0`/`vol_pct: 0.0`. | `analysis/portfolio_opt.py:35,47`| Fixed (pass `list(self.rets.columns)`) |

### Pre-existing in-progress refactor (from git working tree, verified working)
- `webapp/server.py`— F&O analytics refactor: single `iv_surface`reuse,
 `days_to_expiry`-based DTE, NSE-quote fallback, `json_safe`, IST clock in
 `/api/health`, uniform 500 JSON handler. verified.
- `quant/options_analytics.pcr_analysis`— tolerate `ce_volume`/`pe_volume`
 aliases so PCR-by-volume isn't silently zero. 
- `main.py`— default serve port 8000 → **8080**. 
- `webapp/static`— added EMA20 overlay + volume-color fix + formula modal
 `addEventListener`. (frontend)

---

## Model Verification (weekend, yfinance + synthetic)

| Model / Check | Command | Result | Status |
|---------------|---------|--------|--------|
| Black-Scholes + Greeks | `main.py bs --spot 24500 --strike 24600 --days 21 --sigma 15`| CE px=347.63 (Δ.5035, γ.000453, θ-10.51, ν23.44, ρ6.90); PE px=355.81 (puts/calls valid put-call relationship) | |
| Put-call parity | unit tests | parity holds | |
| Volatility suite (6 est + cone) | `main.py vol RELIANCE`| close-close 18.98, EWMA 17.26, Parkinson 15.31, GK 14.54, Yang-Zhang 15.76, next-EWMA 17.11% | |
| ATR percentile regime | part of `vol`| 13.5 (was crashing — now ) | |
| Stochastic (GBM/Merton/Heston) | `main.py simulate RELIANCE --model merton`| calibration σ=0.207, μ=-0.079; paths generated | |
| Position sizing (ATR/Kelly) | `main.py size --entry 2500 --stop 2440`| qty=83, risk ₹4,980, notional ₹207,500 | |
| Backtest engine | `main.py backtest RELIANCE --strategy supertrend_rsi`| return -3.69%, Sharpe -1.25, Win 37.5%, PF 0.76 (computed, costs applied) | |
| All 7 strategies | inline sweep | 5 swing + 2 intraday all `generate()`without error | |
| Portfolio optimizer | `main.py optimize RELIANCE,TCS,HDFCBANK`| max_sharpe RELIANCE 1.0 (ret -5.73/vol 20.71); min_var HDFCBANK .42; HRP balanced (fixed index bug) | |
| Formula library + live example | `main.py formula rsi --symbol RELIANCE`| doc + live example computed | |
| yfinance quote (weekend) | `main.py quote RELIANCE`| ltp 1287, P/E 23.3, sector Energy, MCap 1,741,629 cr | |
| Screener (yfinance) | `main.py screener --top 3`| 12 rows, NaN→null safe | |

---

## Data Sources & Weekend Expectations

| Source | Used by | Weekend status |
|--------|---------|----------------|
| **yfinance (OSINT)** | quotes, history, fundamentals, all models/backtest/optimizer | Works 24/7 (last close) |
| **NSE public API** | option chains, FII/DII, bulk/block deals, delivery % | 403/blocked on weekends + non-browser; re-verify on trading day |
| **Google News / Reddit** | volatility radar buzz | public, works anytime |
| **Zerodha Kite** | live execution | NO KEYS YET — paper mode only until user provides |

### BLOCKED (re-verify on a trading day / after Kite keys)
- NSE option chain (`main.py chain NIFTY`, `/api/options/chain`, greeks-surface) → **degrades gracefully, no crash**; needs a trading day + unblocked NSE session to get real rows.
- FII/DII regime (`main.py fiidii`) → returned real 28-Aug data earlier this session; may vary by day.
- Whale radar (`main.py whales`) → depends on NSE bulk/block endpoints.
- Live execution → `execution/kite_orders.py`is triple-guarded; needs `TRADING_MODE=live`+ Kite tokens (user to supply later).

---

## To-do when APIs arrive
- [ ] Wire Zerodha Kite keys → `.env`, run daily login, validate `execution/kite_orders.py`.
- [ ] Re-test all NSE live endpoints on a trading day (option chain, FII/DII, whales, delivery %).
- [ ] Add tests for the 7 fixes above (regression guards).

---

_Last updated: 2026-08-29 (Sat). 40/40 tests passing. Insight engine + multi-source buzz live._

---

## Session — 2026-08-29 (frontend recovery + insight engine + multi-source buzz)

### Frontend recovery & chart fixes
- `app.js`restored from HEAD after a failed line-collapse; fixed pre-existing `$("#fmClose")?.onclick=`(optional chaining on LHS of assignment — illegal JS). 864 lines, `node --check`clean.
- Dark Chart.js theme re-applied: global `Chart.defaults`+ `polishChart`patcher wired into lazy `regChart`. `regChart`call sites wrapped as `regChart("key", ()=>new Chart(...))`so the old chart is destroyed before a new one binds.
- `.ind-row`global flex rule verified (earlier "block" reading was browser cache).

### Regime-conditioned insight engine (grounded in Knowledge base)
- **NEW** `analysis/insight.py`: 9 regimes classified from `^NSEI`(EMA50/200 + ADX), `^INDIAVIX`(VIX percentile), `FiiDiiTracker.regime_bias()`. Emits verdict / favours / trap / state_vector / confirmations / invalidation / horizon_framework / 18-point checklist, per horizon (multiyear → intraday), grounded in KB Ch.16/17/25.
- **`/api/insights`** (GET, cached 900s) added; **`/api/signals`** embeds `insight`+ accepts `horizon`/`side`.
- **`renderInsight`** (app.js) renders the structured card and is now **awaited** inside `showSignal`(both NO-TRADE and live branches) using embedded `s.insight`(removed a `/api/api/insights`double-prefix re-fetch that 404'd). Verified: "Sideways, low volatility · 100% confidence · NEUTRAL · 9 confirmations".

### Multi-source Social & News Buzz (no API keys)
- **REWRITTEN** `research/osint_news.py`: registry of 6 sources (google_news, livemint, bloomberg, etmarkets, hbl, reddit) with per-source reachability probing + **honest status** (blocked shown, not faked), heuristic sentiment (keyword + authority + recency), symbol-relevance filtering with alias map, curated `top_items`. Buzz score = mentions + sources + tilt, capped 100.
- Buzz card renders headline (score / sources live / mentions / tilt), source reachability badges, curated items (sentiment + authority + relevance + external link). Verified: score 87/100, 3/6 sources live. Reddit fully blocked in this env → degrades gracefully.

### Endpoint hardening
- `/api/signals`degrades gracefully when a symbol has no tradable OHLCV (CRUDEOIL/GOLD): returns direction 0 + `reason: no_tradable_data`+ the regime insight instead of a 500. Fixed `NameError: jsonify`(codebase returns plain dicts).

### Tests
- `tests/test_research.py::test_buzz_degrades_gracefully`updated for the new registry API. **40/40 passing.**

### Dedicated Regime Insights panel (DONE)
- **NEW** `panel-insight`(nav: Regime Insights) + `runInsight()`/ `insightPanel()`in `app.js`: a full dashboard-driven view of the regime engine.
- Layout: verdict banner (regime label + horizon + side + confidence dial), 5 KPI tiles (NIFTY / vs EMA200 / ADX / India VIX pct / FII 5d), State Vector R(t), Horizon Framework (signal-priority hierarchy + common mistakes), Confirmations / Invalidation & kill-switches, and the 18-gate interactive Decision Checklist.
- Horizon (multiyear→intraday) and side (long/flat/short) selectors re-fetch `/api/insights`live; auto-runs on panel open.
- Verified in-browser: renders "Sideways, low volatility · NEUTRAL · 100% confidence", 5 tiles, 18 togglable gates, 12 confirmation/invalidation items, **0 console errors**. Fixed the `CONDItIONAL`verdict typo in `insight.py`.

### 5 new pages + diverse visualization set (DONE — 2026-08-29)
User asked for a bigger, option-rich analytical surface with diverse charts. Built all 5 candidate pages + a dedicated insight panel, wired to the regime engine and existing endpoints. Degrade gracefully on a weekend (NSE blocked).
- **`webapp/static/js/panels.js`** (NEW, ~270 lines, `node --check`clean): shared helpers — `kpi()`, `statCell()`(stat grid, e.g. α/β vs NIFTY), `regimeAxes()`(5-axis radar: Trend/Strength/Fund-flow/Calm/Conviction → norm 0–100), `heatColor()`(diverging hue scale), `gaugeSVG()`(half-dial confidence). Loads after `app.js`(shares `api/num/esc/cls/regChart/$`).
 - ** Decision Dashboard** (`panel-decision`): `Promise.all([insights, universe, overview])`→ regime banner + confidence dial + 4 KPI tiles + state-vector radar + "Gate pass / Top RS" KPIs + "Action plan gated by the regime" table + full-universe table (13 rows). Ranked by `rs_vs_nifty_pct`(no composite score offline — honest, no fake). Verified: radar 305×305, 12 data rows, 0 JS errors.
 - ** Universe & Heatmap** (`panel-heatmap`): `/api/universe`→ diverging sector heatmap (13 groups, 88 cells, hover-to-zoom) + top/bottom mover tables + sector-aggregate horizontal bar. Verified all three render.
 - ** Derivatives Deep-Dive** (`panel-derivatives`): 4 KPIs (structure/near basis/far basis/α·β) + futures term-structure chart + rolling-α chart + α/β stat grid (6 cells: α/β/R²/tracking-err/IR/t-stat) + option-chain table (graceful off-season fallback — NSE 503).
 - ** Market Regime** (`panel-regime`): regime radar + FII/DII flow bars + volatility surface (vol-regime) + 18-gate decision checklist.
 - ** Opportunity Board** (`panel-opportunity`): multi-strategy scan → KPIs + opportunity matrix table + verdict-distribution doughnut + conviction-vs-distance bubble.
- **Backend**: NEW `GET /api/universe`(88-symbol sector heatmap data, cached 1800s). Hardened `GET /api/options/chain`+ `GET /api/volatility`to degrade to **HTTP 503** (was 500) off-season.
- **UI**: nav links for all 5 pages; `#panel-insight`rebuilt in `index.html`; KPI-grid CSS (`kpi`/`statcell`/`.statcell`/`.dv-alpha`/`.heat-*`/`.hm-*`); app.js `nav`auto-load handlers for the 5 new panels.
- **Verified in-browser** (Playwright, off-season/NSE-blocked): all 6 panels render with 0 JS errors; only console entry is a benign NSE 503 (caught by the client), so the pages degrade honestly rather than showing blank.
- **Tests: 40/40 passing.**

### Incident — index.html clobbered (recovered from git)
- A python "read-modify-write" edit to `webapp/static/index.html`did a silent partial match and wiped the 414-line file to 0 bytes (the file was uncommitted since the single initial commit, so nothing was recoverable from the working tree). Restored via `git checkout -- webapp/static/index.html`, which **reverted to HEAD and lost the prior session's insight-panel nav/section + all in-progress UI edits**.
- Everything else (analysis/, quant/, data/, research/, app.js, style.css, server.py) survived because it was already on disk. **All panels were then rebuilt from scratch** in this session.
- **Lesson / guardrail**: for uncommitted files, keep a `cp`backup before any destructive "replace" python edit; assert the marker actually matched (the partial-match returned "done" but matched 0 chars). Prefer `oldString`/`newString`edits that fail loudly over substring `str.replace`that silently no-ops.
- **Remaining scope**: VaR/CVaR + correlation/drawdown risk expansion — ** DONE** (see below).

### Risk Map — correlation · drawdown · concentration (DONE — 2026-08-29)
Built a dedicated **Risk Map** page that turns the previously-dead `risk/manager.py`helpers (`correlation_risk`, drawdown, concentration) into a live visualized panel.
- **Backend**
 - `quant/monte_carlo.py`: `mc_var(...)`gains an optional `distribution=True`flag that returns a 50-bin return histogram + VaR/CVaR line markers. Fixed a swapped `np.histogram`unpack (was `edges, counts`→ now `counts, edges`).
 - `risk/manager.py`: `portfolio_var`forwards `distribution=True`so every VaR call now also yields the simulated return distribution.
 - `webapp/server.py`: new **`GET /api/risk/corrmap`** composite endpoint (VaR/CVaR + correlation clusters + underwater drawdown + concentration: HHI / max-weight / effective-#-bets / avg pairwise corr). 422s on too few overlapping bars; off-season-safe.
- **Frontend**
 - `webapp/static/js/panels.js`: new `window.riskMapPanel()`renders 4 KPI tiles (VaR / CVaR / avg-corr / max-DD), a **6×6 correlation matrix** (diverging DOM heatmap, red=low→green=high), an **underwater chart** (equal-weight portfolio drawdown, ~120 points), a **per-symbol max-DD bar** (worst-first), a **VaR return-distribution histogram** with VaR/CVaR marker bars, **4 concentration stat cells** (HHI, max weight, effective #bets, avg pairwise corr), and a high-correlation cluster table with advice.
 - `webapp/static/index.html`: new `Risk Map`nav link + `#panel-riskmap`section (symbols + horizon + confidence controls). Default symbols = `RELIANCE,TCS,HDFCBANK,INFY,ITC,SBIN`(all valid; `LR`/`TATAMOTORS`fail yfinance resolution).
 - `webapp/static/css/style.css`: `.corr-heat / .corr-row / .corr-rowh / .corr-cell`(flex square grid) added.
 - `webapp/static/js/app.js`: `riskmap`auto-load nav gate (`_rmLoaded`).
- **Tests**: `tests/test_quant.py`+2 (`test_correlation_risk_detects_cluster`, `test_mc_var_distribution_flag`). **42/42 passing.** `mc_var`histogram bug fixed as a side effect (the test caught it).
- **Verified in-browser** (Playwright, off-season): 6 KPIs, 36-cell correlation matrix, 3 charts (all painted 474×237), 4 concentration cells, TCS–INFY 0.76 cluster, **0 console errors.**

