# QuantDesk India 🇮🇳

A full-stack **algorithmic trading & research platform** for the Indian markets (NSE/BSE).  
Built for swing traders, options strategists, and quants who want institutional-grade tools on OSINT data — with a clean path to live Zerodha Kite execution.

---

## 🚀 Quick Start

```bash
# 1. Clone & install
git clone <your-repo> && cd Trading-Project
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. (Optional) Add Zerodha Kite credentials
cp .env.example .env
# edit .env → add KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN

# 3. Launch the web dashboard
python main.py serve
# → http://localhost:8619
```

### CLI One-Liners
```bash
# Market overview
python main.py quote RELIANCE
python main.py screener --top 10
python main.py signal RELIANCE --strategy supertrend_rsi
python main.py backtest RELIANCE --strategy breakout_pullback

# Options & Greeks
python main.py chain NIFTY
python main.py options iron_condor --spot 24500 --sigma 15 --days 21

# Risk & Portfolio
python main.py size --entry 2500 --stop 2440
python main.py optimize RELIANCE,TCS,HDFCBANK

# Deep-dive formulas (click ⓘ in UI)
python main.py formula rsi --symbol RELIANCE
python main.py formula bs_price --symbol NIFTY --S 24500 --K 24600 --T_days 7 --sigma 14
```

---

## 🏗️ Architecture

```
Trading-Project/
├── main.py                    # CLI entry point
├── webapp/
│   ├── server.py              # FastAPI backend (all /api/* routes)
│   └── static/                # SPA dashboard (HTML/CSS/JS)
├── config/settings.py         # Central config (env, universe, risk params)
├── data/
│   ├── providers/             # yfinance (OSINT), NSE (OSINT), Kite (live)
│   └── osint/                 # FII/DII tracker, Whale radar (bulk/block deals, delivery%)
├── quant/
│   ├── black_scholes.py       # Pricing + full Greeks + IV solver (Newton + Brent)
│   ├── binomial.py            # CRR American/European trees
│   ├── monte_carlo.py         # GBM MC pricing, VaR/CVaR sims
│   ├── stochastic.py          # GBM, OU (pairs), Merton Jump, Heston
│   └── volatility.py          # CC, EWMA, Parkinson, GK, YZ, vol cones
├── analysis/
│   ├── indicators.py          # 30+ TA indicators (pure pandas/numpy)
│   ├── screener.py            # Multi-factor swing candidate ranker
│   └── portfolio_opt.py       # Markowitz + HRP efficient frontier
├── strategies/
│   ├── swing.py               # Supertrend+RSI, BB MeanRev, BreakoutPullback, EMACross, WeeklyMom
│   ├── intraday.py            # ORB, CPR trend-day
│   └── options_strategy.py    # Covered call, CSP, spreads, condors, straddles + payoff
├── backtest/engine.py         # Vectorized engine w/ ATR stops, scale-outs, costs
├── risk/manager.py            # Kelly, ATR sizing, portfolio VaR/CVaR, heat limits
├── execution/
│   ├── paper_broker.py        # JSON-persisted paper trading
│   └── kite_orders.py         # Live Kite (triple-guarded)
├── formulas/                  # 77 formulas w/ LaTeX, cascade deps, live examples
│   ├── registry.py            # Central documentation
│   └── examples.py            # Live worked examples on real data
├── research/
│   ├── store.py               # JSON artifact store (save/load/list)
│   ├── osint_news.py          # Google News RSS + Reddit public JSON
│   ├── expiries.py            # F&O expiry calendar rules engine
│   ├── case_shree_refrigerations.py  # Flagship OSINT case study
│   └── volatility_radar.py    # 16 instruments, playbooks, social buzz
└── tests/test_quant.py        # 40 tests (BS parity, CRR→BS, MC CI, ADX, VaR, etc.)
```

---

## 📊 Web Dashboard (http://localhost:8619)

| Panel | What You Get |
|-------|--------------|
| **Dashboard** | Live indices, FII/DII regime gauge, whale prints, paper snapshot |
| **Screener & Signals** | Multi-factor ranked watchlist → one-click signal card with entry/stop/T1/T2/RR + Kelly/ATR sizing → "Add to Paper Book" |
| **Charts & TA** | Lightweight-charts candles + EMA/Supertrend/Bollinger overlays, RSI/MACD panes, volume, live indicator readout |
| **Options Lab** | NSE option chain + Greeks + IV smile + OI walls + PCR/Max Pain + Strategy Builder (Iron Condor, spreads, covered call, CSP, straddle) with payoff chart |
| **Backtest Lab** | Equity curve vs B&H, drawdown, R-multiple histogram, trade log, metrics with ⓘ formula links |
| **Whale Radar** | Bulk/block deals table, per-symbol whale score breakdown (volume + delivery + deals) |
| **Portfolio & Risk** | Position sizer, Kelly optimizer, VaR/CVaR stress, Portfolio Optimizer (MV/HRP), Paper Book manager |
| **Case Study** | **Shree Refrigerations** — symbol resolver → 1y price → surge forensics (last 10 vs prior 60) → 27 pattern events (P1-P5) → 5 weighted hypotheses → competitor RS → curated KB (news/financials/risks) → analyst notes saved to research store |
| **Volatility Radar** | 16 instruments ranked by Yang-Zhang vol, percentiles, expiry calendar, strategy playbook, Google News + Reddit buzz |
| **Formula Library** | Searchable registry; click any ⓘ in UI for LaTeX math, step-by-step derivation, cascade deps, **live worked example on current market data** |

### ⓘ Formula Explainability
Every metric in the UI has a blue **ⓘ** icon. Clicking it opens a modal with:
- **LaTeX math** (KaTeX rendered)
- **Plain-English text formula**
- **Numbered derivation steps**
- **Input table**
- **Trading interpretation**
- **Static worked example**
- **Live worked example** (re-computed on current data for that symbol)
- **Cascading dependency tree** (click child → expand inline)

---

## 🔬 OSINT Data Sources (No API Keys Required)

| Source | Endpoints Used | Coverage |
|--------|----------------|----------|
| **Yahoo Finance** | `yfinance` batch download | 90+ NSE equities OHLCV, indices, 1y-5y history |
| **NSE India** (public API) | `/api/option-chain-*`, `/api/report/bulk-deals`, `/api/fiidiiTradeReact`, `/api/report/delivery-data` | Option chains (indices + equities), bulk/block deals, FII/DII cash flows, delivery % |
| **Google News RSS** | `/rss/search?q=...` | Headlines per symbol/query |
| **Reddit Public JSON** | `/search.json?q=...&sort=top&t=month` | Mention counts + top posts (rate-limited, degrades gracefully) |

> **No credentials needed** for full functionality. Add Kite keys only when you want live execution.

---

## ⚙️ Connecting Zerodha Kite (Live Execution)

1. Register at https://developers.kite.trade → create app → get `API_KEY` & `API_SECRET`.
2. Add to `.env`:
   ```env
   KITE_API_KEY=your_key
   KITE_API_SECRET=your_secret
   ```
3. Run daily login flow:
   ```bash
   python -c "from kiteconnect import KiteConnect; k=KiteConnect('YOUR_KEY'); print(k.login_url())"
   ```
   Open URL → login → copy `request_token` from redirect URL → set:
   ```env
   KITE_ACCESS_TOKEN=your_request_token
   TRADING_MODE=live
   ```
4. **Safety**: Live orders require explicit `confirm=True` in every call. The paper broker is the default.

---

## 📈 Key Quantitative Features

### Black-Scholes + Greeks
- Vectorized `bs_price`, `greeks` (Δ, Γ, Θ, ν, ρ) for entire chains
- IV solver: Newton-Raphson (fast) + Brent fallback (robust)
- Put-call parity check, payoff diagram generator

### Stochastic Models
- **GBM** exact simulation (antithetic MC)
- **Ornstein-Uhlenbeck** for pairs/spread mean-reversion (calibrated via OLS, half-life output)
- **Merton Jump Diffusion** (Poisson-compensated log-normal jumps) for fat-tail stress
- **Heston** stochastic volatility (full-truncation Euler, negative ρ for Indian skew)

### Volatility Suite
- 6 estimators: Close-Close, EWMA (λ=0.94), Parkinson, Garman-Klass, Rogers-Satchell, **Yang-Zhang** (best for Indian gappy data)
- Volatility cone (5/10/21/42/63d percentiles)
- ATR percentile regime gauge

### Risk Management
- **ATR-based sizing**: `qty = (capital × risk%) / (2 × ATR)`
- **Half-Kelly** with win-rate/RR estimates
- Portfolio VaR/CVaR (historical + Monte Carlo)
- Heat limit (max 8% aggregate risk), correlation-aware clustering

### Backtesting
- Vectorized loop, ATR stops, +1R scale-out, trailing after T1, time stop
- Realistic costs: brokerage + STT + slippage
- Metrics: CAGR, Sharpe, Sortino, Calmar, MaxDD, Win%, PF, Expectancy, Avg R, Exposure%

---

## 🧪 Tests
```bash
pytest tests/ -q
# 40 passing: BS parity, CRR→BS convergence, MC CI coverage, ADX non-neg, 
# VaR monotonic, OU half-life, formula registry integrity, live examples, etc.
```

---

## 🔒 Safety & Guardrails

- **Default = PAPER MODE**. Live execution requires `TRADING_MODE=live` + valid Kite tokens + `confirm=True` on every call.
- **Heat limits**: max 8% aggregate risk, 10 concurrent positions, 1% per trade default.
- **No lookahead**: backtest uses next-open fills, signals evaluated on closed bars only.
- **OSINT only** by default — no proprietary data dependencies.
- **Explicit opt-in** for every live action.

---

## 🗂️ Research Artifacts (Auto-Persisted)

All generated dossiers are saved under `research/store/`:
- `case_studies/shree_refrigerations/symbol_resolution.json`
- `case_studies/shree_refrigerations/case_full.json` (full dossier)
- `case_studies/shree_refrigerations/analyst_notes.json`
- `radar/snapshots/radar_scan_*.json`
- `radar/buzz/...`
- `portfolio_optimizations/...`

List them: `GET /api/research/files` or `python main.py list-research`.

---

## 📝 Extending the System

| Want to… | Do this |
|----------|---------|
| Add a new swing strategy | Subclass `StrategyBase` in `strategies/swing.py`, register in `SWING_STRATEGIES` |
| Add a new indicator | Pure pandas function in `analysis/indicators.py` + add ⓘ entry in `formulas/registry.py` |
| Add a new OSINT source | Implement `fetch()` in `data/osint/` + wire into `FiiDiiTracker`/`WhaleTracker` |
| Add a new formula doc | `_add(FormulaDoc(...))` in `formulas/registry.py` |
| Add a new radar instrument | Add entry to `RADAR_INSTRUMENTS` in `research/expiries.py` |
| Add a new expiry rule | Extend `next_expiries()` in `research/expiries.py` |

---

## 📚 Key References Embedded

- Black-Scholes-Merton (1973), Merton (1976) jump diffusion
- Heston (1993) stochastic volatility
- Ornstein-Uhlenbeck (1930) mean reversion
- Yang-Zhang (2000) OHLC volatility estimator
- Lopez de Prado (2016) Hierarchical Risk Parity
- Kelly (1956) criterion, Vince (1990) fractional Kelly
- NSE India F&O specifications (lot sizes, strike intervals, expiry calendar)

---

## 🤝 Contributing

PRs welcome! Priority areas:
- More pattern detectors for Case Study engine
- NSE SME board data enrichment
- Options IV surface interpolation
- Portfolio stress-test scenarios
- More social sources (Twitter API, YouTube transcripts)

---

## ⚠️ Disclaimer

**This software is for research and educational purposes.**  
- Past performance ≠ future results.  
- OSINT data may be delayed, incomplete, or incorrect.  
- Trading derivatives carries substantial risk of loss.  
- **Never trade with money you cannot afford to lose.**  
- Verify every signal, size, and assumption independently.

---

## 📄 License

MIT — use freely, attribute if you fork.

---

**Built with:** Python 3.13, FastAPI, NumPy, Pandas, SciPy, yfinance, Lightweight-Charts, Chart.js, KaTeX.  
**Architecture philosophy:** *Every number has a formula. Every formula has a source. Every source is traceable.*