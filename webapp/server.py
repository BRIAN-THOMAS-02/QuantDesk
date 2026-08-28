"""QuantDesk India - API server powering the web dashboard.

Run:  python main.py serve   (or: uvicorn webapp.server:app --reload --port 8000)
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

from config import settings
from utils.helpers import to_yf_symbol, market_phase, logger
from data.providers.yfinance_provider import YFinanceProvider
from data.providers.nse_provider import NSEProvider
from data.osint.fii_dii import FiiDiiTracker
from data.osint.whale_tracker import WhaleTracker
from analysis.indicators import (compute_all, ema, bollinger, supertrend,
                                 macd as ta_macd, rsi as ta_rsi, adx as ta_adx,
                                 atr as ta_atr)
from analysis.screener import Screener
from analysis.portfolio_opt import PortfolioOptimizer
from strategies.swing import SWING_STRATEGIES
from quant import (futures_fair_value, futures_basis, cash_futures_arbitrage,
                   futures_greeks, term_structure_analysis, roll_yield,
                   atm_iv, skew_metrics, term_structure_iv, iv_smile,
                   put_call_parity, max_pain, pcr_analysis, oi_walls,
                   oi_change_analysis, position_greeks, delta_neutral_hedge,
                   gamma_scalping_pnl, calendar_spread_analysis,
                   diagonal_spread_analysis, span_margin_estimate,
                   scenario_analysis, implied_dividend_yield, implied_forward_rate,
                   complete_fno_dashboard, instrument_fno_analytics,
                   capm_alpha_beta, rolling_alpha_beta)
from strategies.intraday import INTRADAY_STRATEGIES
from strategies.options_strategy import OptionsStrategyEngine, oi_intelligence
from backtest.engine import run_backtest, BTConfig
from risk.manager import RiskManager
from quant.black_scholes import bs_price, greeks, implied_vol, greek_chain
from quant.monte_carlo import simulate_gbm, terminal_distribution_stats
from quant.stochastic import MertonJumpDiffusion, Heston, estimate_gbm_params
from quant.volatility import (vol_cone, close_to_close, ewma_vol, parkinson,
                              garman_klass, rogers_satchell, yang_zhang,
                              atr_percentile, forecast_ewma_next)
from formulas import REGISTRY, CATEGORIES, get_doc, tree, live_example
from execution.paper_broker import PaperBroker
from research import store as research_store
from research.case_shree_refrigerations import (CaseStudyEngine, analyst_notes,
                                                save_note, SLUG as CASE_SLUG)
from research.volatility_radar import VolatilityRadar
from research.osint_news import buzz as social_buzz
from research.expiries import RADAR_INSTRUMENTS

app = FastAPI(title="QuantDesk India", version="1.0")
STATIC = Path(__file__).parent / "static"

yf_prov = YFinanceProvider()
nse = NSEProvider()
risk = RiskManager()
paper = PaperBroker()

# ------------------------------------------------------------------ #
# tiny TTL cache for slow OSINT calls
# ------------------------------------------------------------------ #
_CACHE: dict[str, tuple[float, object]] = {}


def cached(key: str, ttl: int, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (time.time(), val)
    return val


def df_history(symbol: str, period: str = "2y") -> pd.DataFrame:
    return cached(f"hist:{symbol}:{period}", 600,
                  lambda: yf_prov.history(symbol, period))


def df_with_indicators(symbol: str, period: str = "2y") -> pd.DataFrame:
    return cached(f"ind:{symbol}:{period}", 600,
                  lambda: compute_all(df_history(symbol, period)))


def days_to_expiry(expiry_str: str) -> int:
    try:
        exp = pd.to_datetime(expiry_str, format="%d-%b-%Y", errors="coerce")
    except (ValueError, TypeError):
        exp = pd.to_datetime(expiry_str, errors="coerce")
    if pd.isna(exp):
        try:
            exp = pd.to_datetime(expiry_str, dayfirst=True, errors="coerce")
        except Exception:
            return 7
    return max((exp - pd.Timestamp.now()).days, 0)


def ctx_for(symbol: str, params: dict | None = None) -> dict:
    return {"symbol": symbol.upper(), "df": df_history(symbol),
            "spot": None, "provider": yf_prov, "params": params or {}}


# =================================================================== #
# MARKET OVERVIEW / OSINT
# =================================================================== #
@app.get("/api/health")
def health():
    return {"ok": True, "mode": settings.TRADING_MODE,
            "kite_configured": bool(settings.KITE_API_KEY),
            "phase": market_phase(),
            "time_ist": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}


@app.get("/api/market/overview")
def overview():
    def fetch():
        out = []
        for name, sym in settings.INDICES.items():
            try:
                q = yf_prov.quote(sym)
                out.append({"name": name, **q})
            except Exception:
                continue
        return out
    indices = cached("overview", 120, fetch)

    def regime():
        return FiiDiiTracker().regime_bias()
    regime_d = cached("regime", 1800, regime)
    return {"indices": indices, "regime": regime_d, "phase": market_phase()}


@app.get("/api/market/fii-dii")
def fii_dii():
    def fetch():
        t = FiiDiiTracker()
        return {"table": t.latest().tail(20).to_dict("records"),
                "regime": t.regime_bias()}
    return cached("fiidii", 1800, fetch)


@app.get("/api/market/deals")
def deals(type_: str = Query("whale_table", alias="type"), days: int = 3):
    def fetch():
        wt = WhaleTracker()
        if type_ == "summary":
            return wt.symbol_summary(days=days).to_dict("records")
        return wt.whale_table(days=days).head(60).to_dict("records")
    key = f"deals:{type_}:{days}"
    rows = cached(key, 900, fetch) or []
    return {"rows": rows}


@app.get("/api/market/delivery/{symbol}")
def delivery(symbol: str):
    def fetch():
        d = nse.delivery_data(symbol)
        return d.tail(30).to_dict("records") if not d.empty else []
    return {"symbol": symbol.upper(),
            "rows": cached(f"deliv:{symbol}", 3600, fetch)}


@app.get("/api/market/whale/{symbol}")
def whale(symbol: str):
    def fetch():
        hist = df_history(symbol)
        try:
            deliv = nse.delivery_data(symbol)
        except ConnectionError:
            deliv = pd.DataFrame()
        try:
            deals_df = nse.bulk_deals(days=5)
        except ConnectionError:
            deals_df = pd.DataFrame()
        return WhaleTracker().score_symbol(symbol, hist, deliv, deals_df)
    return cached(f"whale:{symbol}", 1800, fetch)


# =================================================================== #
# QUOTES / HISTORY + CHART PAYLOADS
# =================================================================== #
@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    try:
        return yf_prov.quote(symbol)
    except Exception as e:
        raise HTTPException(502, f"quote failed: {e}")


@app.get("/api/history/{symbol}")
def history(symbol: str, period: str = "6mo", interval: str = "1d"):
    if interval != "1d":
        raw = cached(f"histi:{symbol}:{interval}", 300,
                     lambda: yf_prov.history(symbol, "5d", interval))
    else:
        raw = df_history(symbol, period if period in ("6mo", "1y", "2y", "max") else "6mo")
    if raw.empty:
        raise HTTPException(404, "no data")
    ind = compute_all(raw)
    bb = bollinger(ind.close)
    st = supertrend(ind)

    def series(s, nd=2):
        s = s.dropna()
        return [[int(pd.Timestamp(t).timestamp()), round(float(v), nd)]
                for t, v in s.items()]

    candles = [[int(pd.Timestamp(t).timestamp()),
                round(float(r.open), 2), round(float(r.high), 2),
                round(float(r.low), 2), round(float(r.close), 2)]
               for t, r in raw.iterrows()]
    vols = [[int(pd.Timestamp(t).timestamp()), int(v)] for t, v in raw.volume.items()]
    m = ta_macd(ind.close); r14 = ta_rsi(ind.close)
    return {
        "symbol": symbol.upper(),
        "candles": candles,
        "overlays": {
            "ema20": series(ema(ind.close, 20)),
            "ema50": series(ema(ind.close, 50)),
            "ema200": series(ema(ind.close, 200)),
            "bb_upper": series(bb.upper), "bb_lower": series(bb.lower),
            "supertrend": series(st.supertrend), "st_dir": st.direction.tolist(),
        },
        "volume": vols,
        "sub": {
            "rsi": series(r14),
            "macd": series(m.macd), "macd_sig": series(m.signal),
            "macd_hist": [ [int(pd.Timestamp(t).timestamp()), round(float(v), 3)]
                           for t, v in (m.macd - m.signal).dropna().items()],
        },
        "snapshot": {
            "rsi": round(float(r14.iloc[-1]), 1),
            "adx": round(float(ta_adx(ind).adx.iloc[-1]), 1),
            "atr": round(float(ta_atr(ind).iloc[-1]), 2),
            "atr_pct": round(float(ta_atr(ind).iloc[-1] / ind.close.iloc[-1] * 100), 2),
            "st_dir": int(st.direction.iloc[-1]),
            "volz": round(float(((raw.volume - raw.volume.rolling(20).mean())
                                 / raw.volume.rolling(20).std()).iloc[-1]), 2),
            "pct_from_52wh": round((float(ind.close.iloc[-1]) /
                                    float(ind.close.rolling(252, min_periods=60).max().iloc[-1])
                                    - 1) * 100, 1),
        },
    }


# =================================================================== #
# SCREENER & SIGNALS
# =================================================================== #
@app.get("/api/screener")
def screener(top_n: int = 12, universe: str | None = None, refresh: bool = False):
    uni = universe.split(",") if universe else None

    def run():
        sc = Screener(universe=uni)
        # batch-download for speed
        syms = sc.universe
        data = yf.download([to_yf_symbol(s) for s in syms], period="1y",
                           group_by="ticker", threads=True, progress=False)
        for s in syms:
            try:
                sub = data[to_yf_symbol(s)] if len(syms) > 1 else data
                if isinstance(sub.columns, pd.MultiIndex):  # safety
                    sub.columns = sub.columns.get_level_values(-1)
                if sub is not None and not sub.dropna().empty:
                    from analysis.indicators import compute_all as ca
                    sc._cache[s] = ca(sub.rename(columns=str.lower))
            except (KeyError, AttributeError, IndexError):
                continue
        res = sc.run(top_n=top_n)
        return res.to_dict("records")
    rows = cached(f"screener:{top_n}:{universe}", 1800, run)
    return {"rows": rows, "generated_at": datetime.now().isoformat(timespec="seconds"),
            "factors_doc": "screener_composite"}


class SignalRequest(BaseModel):
    symbol: str
    strategy: str = "supertrend_rsi"


@app.post("/api/signals")
def signals(req: SignalRequest):
    cls = SWING_STRATEGIES.get(req.strategy) or INTRADAY_STRATEGIES.get(req.strategy)
    if cls is None:
        raise HTTPException(400, f"unknown strategy {req.strategy}")
    strat = cls(); strat.symbol = req.symbol.upper()
    df = df_with_indicators(strat.symbol)
    sig = strat.generate(df).as_dict()

    # enrich with risk sizing when actionable
    if sig["direction"] == 1 and sig.get("stop"):
        size = risk.atr_position_size(sig["entry"], sig["stop"])
        sig["sizing"] = size
        if sig.get("target1") is None:
            t1, t2 = risk.targets_from_rr(sig["entry"], sig["stop"])
            sig["target1"], sig["target2"] = t1, t2
    sig["regime"] = cached("regime", 1800, lambda: FiiDiiTracker().regime_bias())
    return sig


@app.get("/api/strategies")
def strategies():
    out = []
    for reg in (SWING_STRATEGIES, INTRADAY_STRATEGIES):
        for n, c in reg.items():
            out.append({"id": n, "name": c.name, "holding": c.holding_period,
                        "description": c.description})
    return {"strategies": out}


# =================================================================== #
# BACKTEST
# =================================================================== #
class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "supertrend_rsi"
    period: str = "2y"
    capital: float = Field(default=settings.CAPITAL, gt=10_000)
    risk_pct: float = Field(default=settings.RISK_PER_TRADE_PCT, gt=0, le=5)
    atr_mult: float = Field(default=2.0, ge=0.5, le=5)
    max_hold_days: int = Field(default=20, ge=2, le=120)


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    cls = SWING_STRATEGIES.get(req.strategy)
    if cls is None:
        raise HTTPException(400, "backtesting supports swing strategies only")
    df = df_with_indicators(req.symbol, req.period)
    if len(df) < 220:
        raise HTTPException(422, f"insufficient history ({len(df)} bars)")
    entries = cls().entries(df)
    cfg = BTConfig(capital=req.capital, risk_pct=req.risk_pct,
                   atr_mult_stop=req.atr_mult, max_hold_days=req.max_hold_days)
    res = run_backtest(df, entries, cfg, req.symbol.upper(), req.strategy)
    bench = df.close / df.close.iloc[0] * req.capital

    def ds(series: pd.Series, pts: int = 480):
        step = max(len(series) // pts, 1)
        s = series.iloc[::step]
        return [[int(pd.Timestamp(t).timestamp()), round(float(v), 0)]
                for t, v in s.items()]
    eq_ds = ds(res.equity); bh_ds = ds(bench)
    dd = (res.equity / res.equity.cummax() - 1) * 100
    return {
        "metrics": res.metrics,
        "equity": eq_ds, "buy_hold": bh_ds, "drawdown": ds(dd),
        "trades": res.trades.tail(80).to_dict("records"),
        "params": req.model_dump(),
        "metric_docs": ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown",
                        "win_rate", "profit_factor", "calmar_ratio", "exposure_time"],
    }


# =================================================================== #
# OPTIONS LAB
# =================================================================== #
INDEX_UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]


@app.get("/api/options/expiries/{underlying}")
def option_expiries(underlying: str):
    def fetch():
        return nse.expiries(underlying)
    try:
        return {"expiries": cached(f"exp:{underlying}", 1800, fetch)}
    except ConnectionError as e:
        raise HTTPException(503, f"NSE unavailable: {e}")


@app.get("/api/options/chain")
def option_chain(underlying: str, expiry: str | None = None):
    def fetch():
        ch = nse.option_chain(underlying, expiry)
        dte = days_to_expiry(expiry) if expiry else \
            days_to_expiry(ch.expiry.iloc[0])
        ch = greek_chain(ch, r=settings.RISK_FREE_RATE, days_to_expiry=dte)
        intel = oi_intelligence(ch)
        return {"expiry_used": ch.expiry.iloc[0], "dte": dte,
                "chain": ch.round(2).to_dict("records"), "intel": intel}
    key = f"chain:{underlying}:{expiry}"
    try:
        return cached(key, 300, fetch)
    except ConnectionError as e:
        raise HTTPException(503, f"NSE unavailable: {e}")


class PresetRequest(BaseModel):
    preset: str = "iron_condor"
    spot: float
    sigma: float = 0.15
    days: int = 21
    width: int = 200
    wing: int = 400
    body: int = 150
    otm_pct: float = 0.03


PRESET_MAP = {"covered_call": "covered_call", "cash_secured_put": "cash_secured_put",
              "bull_call_spread": "bull_call_spread", "iron_condor": "iron_condor",
              "straddle": "straddle_analysis"}


@app.post("/api/options/preset")
def options_preset(req: PresetRequest):
    eng = OptionsStrategyEngine(spot=req.spot, r=settings.RISK_FREE_RATE)
    fn = getattr(eng, PRESET_MAP[req.preset])
    kwargs = {"sigma_s": req.sigma, "days": req.days}
    if req.preset == "bull_call_spread":
        kwargs["width"] = req.width
    elif req.preset == "iron_condor":
        kwargs.update(wing=req.wing, body=req.body)
    elif req.preset in ("covered_call", "cash_secured_put"):
        kwargs["otm_pct"] = req.otm_pct
    return fn(**kwargs)


# =================================================================== #
# VOLATILITY / MODELS / RISK / PORTFOLIO
# =================================================================== #
@app.get("/api/volatility/{symbol}")
def volatility(symbol: str):
    def fetch():
        df = df_history(symbol, "2y")
        est = estimate_gbm_params(df.close)
        return {
            "gbm": est,
            "cone": vol_cone(df.close).to_dict("records"),
            "estimators": [
                {"name": "Close-Close", "val": round(float(close_to_close(df.close, 21).iloc[-1] * 100), 2)},
                {"name": "EWMA λ=.94", "val": round(float(ewma_vol(df.close).iloc[-1] * 100), 2)},
                {"name": "Parkinson", "val": round(float(parkinson(df.high, df.low, 21).iloc[-1] * 100), 2)},
                {"name": "Garman-Klass", "val": round(float(garman_klass(df.high, df.low, df.open, df.close, 21).iloc[-1] * 100), 2)},
                {"name": "Rogers-Satchell", "val": round(float(rogers_satchell(df.high, df.low, df.open, df.close, 21).iloc[-1] * 100), 2)},
                {"name": "Yang-Zhang", "val": round(float(yang_zhang(df.high, df.low, df.open, df.close, 21).iloc[-1] * 100), 2)},
            ],
            "atr_percentile": atr_percentile(df.high, df.low, df.close),
            "next_day_ewma_forecast_pct": forecast_ewma_next(df.close),
        }
    return cached(f"vol:{symbol}", 1800, fetch)


class SimulateRequest(BaseModel):
    symbol: str = "RELIANCE"
    model: str = "gbm"          # gbm|merton|heston
    horizon_days: int = 126
    n_paths: int = 3000
    mu: float | None = None
    sigma: float | None = None
    jump_intensity: float = 4.0
    kappa: float = 5.0
    theta_v: float | None = None
    xi: float = 0.9
    rho: float = -0.7


@app.post("/api/models/simulate")
def models_simulate(req: SimulateRequest):
    df = df_history(req.symbol, "2y")
    cal = estimate_gbm_params(df.close)
    S0 = float(df.close.iloc[-1])
    mu = req.mu if req.mu is not None else cal["mu_annual"]
    sigma = req.sigma if req.sigma is not None else cal["sigma_annual"]
    T = req.horizon_days / 252

    if req.model == "merton":
        paths = MertonJumpDiffusion(mu, sigma, req.jump_intensity,
                                    -0.03, 0.05).simulate(S0, T=T,
                                                          steps=req.horizon_days,
                                                          n_paths=req.n_paths, seed=11)
    elif req.model == "heston":
        tv = (req.theta_v if req.theta_v is not None else sigma ** 2)
        paths, _ = Heston(req.kappa, tv, req.xi, req.rho).simulate(
            S0, mu, T=T, steps=req.horizon_days, n_paths=req.n_paths, seed=13)
    else:
        paths = simulate_gbm(S0, mu, sigma, T=T, steps=req.horizon_days,
                             n_paths=req.n_paths, seed=42)

    pct = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    step = max(req.horizon_days // 120, 1)
    idx = list(range(0, req.horizon_days + 1, step))
    if idx[-1] != req.horizon_days:
        idx.append(req.horizon_days)
    bands = {p: [round(float(x), 1) for x in pct[i, idx]]
             for i, p in enumerate(["p5", "p25", "p50", "p75", "p95"])}
    stats = terminal_distribution_stats(paths[:, ::step][:, :len(idx)])
    stats.update({"model": req.model, "S0": S0,
                  "mu_annual": round(mu, 4), "sigma_annual": round(sigma, 4)})
    return {"bands": bands, "x": idx, "stats": stats}


class SizeRequest(BaseModel):
    entry: float
    stop: float
    capital: float = settings.CAPITAL
    risk_pct: float = settings.RISK_PER_TRADE_PCT


@app.post("/api/risk/size")
def risk_size(req: SizeRequest):
    rm = RiskManager(req.capital)
    return rm.atr_position_size(req.entry, req.stop, req.risk_pct)


class KellyRequest(BaseModel):
    win_rate: float = Field(gt=0.01, lt=1)
    rr: float = Field(gt=0.05)
    capital: float = settings.CAPITAL


@app.post("/api/risk/kelly")
def risk_kelly(req: KellyRequest):
    return RiskManager(req.capital).kelly_size(req.win_rate, req.rr)


class VaRRequest(BaseModel):
    symbols: list[str]
    weights: list[float] | None = None
    value: float = settings.CAPITAL
    horizon_days: int = 5
    alpha: float = 0.95


@app.post("/api/risk/var")
def risk_var(req: VaRRequest):
    cols = {}
    for s in req.symbols[:12]:
        h = df_history(s, "1y")
        cols[s.upper()] = h.close.pct_change()
    rets = pd.DataFrame(cols).dropna(how="any")
    if rets.empty:
        raise HTTPException(422, "no overlapping returns; check symbols")
    w = req.weights
    if w:
        tot = sum(w) or 1
        w = [x / tot for x in w]
    return RiskManager().portfolio_var(rets, value=req.value, weights=w,
                                       alpha=req.alpha,
                                       horizon_days=req.horizon_days)


@app.get("/api/portfolio/optimize")
def portfolio_opt(symbols: str, method: str = "all"):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:15]
    if len(syms) < 2:
        raise HTTPException(422, "need >=2 symbols")
    cols = {}
    for s in syms:
        h = df_history(s, "2y")
        cols[s] = h.close
    prices = pd.DataFrame(cols).dropna(how="any")
    opt = PortfolioOptimizer(prices)
    summ = opt.summary()
    frontier = opt.efficient_frontier(20)
    corr = prices.pct_change().corr().round(2)
    return {"summary": summ, "frontier": frontier,
            "symbols": syms,
            "correlation": {"labels": corr.columns.tolist(),
                            "matrix": corr.values.tolist()}}


# =================================================================== #
# PAPER BOOK
# =================================================================== #
class PaperOrder(BaseModel):
    symbol: str
    side: str = "BUY"
    qty: int = Field(gt=0)
    price: float = Field(gt=0)
    tag: str | None = None


@app.post("/api/paper/order")
def paper_order(o: PaperOrder):
    return paper.place_order(o.symbol, o.side, o.qty, o.price, tag=o.tag)


@app.get("/api/paper/portfolio")
def paper_portfolio():
    syms = {s for s, p in paper.state["positions"].items() if p["qty"] > 0}
    prices = {}
    for s in syms:
        try:
            prices[s] = yf_prov.quote(s)["ltp"]
        except Exception:
            continue
    return paper.portfolio(prices)


@app.get("/api/paper/orders")
def paper_orders():
    return {"orders": paper.orders()[-60:]}


# =================================================================== #
# FORMULA EXPLAINABILITY API
# =================================================================== #
@app.get("/api/formulas")
def formulas_list():
    return {"categories": CATEGORIES,
            "registry": {cat: sorted(ids) for cat, ids in
                         {k: [f.id for f in REGISTRY.values() if f.category == k]
                          for k in CATEGORIES}.items()}}


@app.get("/api/formula/{fid}")
def formula_detail(fid: str, symbol: str = "RELIANCE",
                   S: float | None = None, K: float | None = None,
                   T_days: float | None = None, sigma: float | None = None,
                   depth: int = 1):
    doc = get_doc(fid)
    if doc is None:
        raise HTTPException(404, f"formula '{fid}' unknown")
    params = {"S": S, "K": K, "T_days": T_days, "sigma": sigma}
    ex = live_example(fid, ctx_for(symbol, params))
    payload = tree(fid, depth=depth)
    payload["live_example"] = ex
    payload["example_symbol"] = symbol.upper() if ex else None
    return payload


# =================================================================== #
# CASE STUDY / RESEARCH
# =================================================================== #
case_engine = CaseStudyEngine()


@app.get("/api/case/{slug}/full")
def case_full(slug: str, refresh: bool = False):
    if slug != CASE_SLUG:
        raise HTTPException(404, f"no case study '{slug}' yet (have: {CASE_SLUG})")
    try:
        payload = cached(f"case:{slug}:{refresh}", 1800 if not refresh else 1,
                         lambda: case_engine.build(refresh=refresh))
        return payload
    except Exception as e:
        logger.exception("case study failed")
        raise HTTPException(502, f"case build failed: {e}")


@app.get("/api/case/{slug}/notes")
def case_notes(slug: str):
    return {"notes": analyst_notes(slug)}


class NoteRequest(BaseModel):
    text: str = Field(min_length=2, max_length=4000)


@app.post("/api/case/{slug}/notes")
def case_add_note(slug: str, req: NoteRequest):
    return save_note(slug, req.text)


@app.get("/api/research/files")
def research_files():
    return {"artifacts": research_store.list_artifacts()}


# =================================================================== #
# VOLATILITY RADAR
# =================================================================== #
radar = VolatilityRadar()


@app.get("/api/radar/instruments")
def radar_instruments():
    def fetch():
        return radar.scan()
    rows = cached("radar_scan", 1200, fetch) or []
    return {"rows": rows,
            "generated_at": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/radar/study/{instrument}")
def radar_study(instrument: str):
    try:
        key = f"radar_study:{instrument}"
        return cached(key, 900, lambda: radar.study(instrument))
    except KeyError:
        raise HTTPException(404, f"unknown instrument {instrument}")
    except Exception as e:
        raise HTTPException(502, f"study failed: {e}")


@app.get("/api/radar/buzz/{instrument}")
def radar_buzz(instrument: str):
    meta = RADAR_INSTRUMENTS.get(instrument.upper())
    query_extra = [f"{meta['label']}" ] if meta else []
    def fetch():
        return social_buzz(instrument.upper(), extra_queries=query_extra)
    return cached(f"buzz:{instrument}", 1500, fetch)


# =================================================================== #
# F&O ANALYTICS
# =================================================================== #

class FNORequest(BaseModel):
    symbol: str
    expiry: str | None = None
    spot: float | None = None
    futures_price: float | None = None


@app.get("/api/fno/analytics/{symbol}")
def fno_analytics(symbol: str, expiry: str | None = None):
    """Complete F&O analytics for one instrument."""
    try:
        sym = symbol.upper()
        # Get spot from yfinance
        q = yf_prov.quote(sym)
        spot = q.get("ltp") or q.get("prev_close", 0)
        if not spot:
            raise HTTPException(404, f"no price data for {sym}")
        
        # Get futures price and chain from NSE
        try:
            # Get futures price from NSE
            nse_quote = nse.quote(sym)
            futures_price = nse_quote.get("ltp") or spot
            dte = 30  # approximate
            
            # Get option chain
            chain = nse.option_chain(sym, expiry)
            chain_iv = iv_surface(chain, spot) if not chain.empty else pd.DataFrame()
            
            # Get historical returns for alpha/beta
            hist = yf_prov.history(sym, "1y")
            returns = hist["close"].pct_change().dropna()
            bench_hist = yf_prov.history("^NSEI", "1y")
            bench_returns = bench_hist["close"].pct_change().dropna()
            
            # Complete analytics
            result = complete_fno_dashboard(sym, spot, futures_price, 30, 
                                            chain, returns, bench_returns)
            
            # Add more detailed analytics
            if not chain.empty:
                result["skew"] = skew_metrics(iv_surface(chain, spot), spot)
                result["iv_term_structure"] = term_structure_iv(
                    iv_surface(chain, spot), spot).to_dict("records")
                result["pcr"] = pcr_analysis(chain)
                result["max_pain"] = max_pain(chain)
                result["oi_walls"] = oi_walls(chain)
                result["parity"] = put_call_parity(chain, spot).to_dict("records")
                result["skew_metrics"] = skew_metrics(iv_surface(chain, spot), spot)
                
                # Calendar spreads
                if "expiry" in chain.columns:
                    expiries = chain["expiry"].unique()
                    if len(expiries) >= 2:
                        exp = sorted(expiries)
                        near_chain = chain[chain["expiry"] == exp[0]]
                        far_chain = chain[chain["expiry"] == exp[1]]
                        result["calendar_spreads"] = calendar_spread_analysis(
                            near_chain, far_chain, spot)
                        result["diagonals"] = diagonal_spread_analysis(chain, spot)
            
            # Futures analytics
            result["futures"] = {
                "spot": spot,
                "futures_price": futures_price,
                "dte": 30,
                "fair_value": futures_fair_value(spot, settings.RISK_FREE_RATE, 0, 30),
                "basis": futures_basis(spot, futures_price, 30),
                "arb": cash_futures_arbitrage(spot, futures_price, 30),
                "greeks": futures_greeks(spot, futures_price, 30).__dict__,
                "margin": futures_margin_estimate(futures_price, 50),
            }
            
            # Alpha/Beta
            hist = yf_prov.history(sym, "1y")
            returns = hist["close"].pct_change().dropna()
            bench_hist = yf_prov.history("^NSEI", "1y")
            bench_returns = bench_hist["close"].pct_change().dropna()
            ab = capm_alpha_beta(returns, bench_returns)
            result["alpha_beta"] = ab.__dict__
            
            return result
            
        except Exception as e:
            logger.exception("F&O analytics failed")
            raise HTTPException(502, f"F&O analytics failed: {e}")


# Additional F&O endpoints
@app.get("/api/fno/futures/term-structure/{symbol}")
def futures_term_structure(symbol: str):
    """Futures term structure from multiple expiries."""
    try:
        sym = symbol.upper()
        q = yf_prov.quote(sym)
        spot = q.get("ltp") or q.get("prev_close", 0)
        
        # Get multiple expiry futures from NSE (simplified)
        # In reality, would fetch from NSE F&O segment
        expiries_data = [
            {"expiry": "2026-09-25", "futures_price": spot * 1.005, "dte": 30},
            {"expiry": "2026-10-30", "futures_price": spot * 1.012, "dte": 60},
            {"expiry": "2026-11-27", "futures_price": spot * 1.018, "dte": 90},
        ]
        return term_structure_analysis(expiries_data, spot)
    except Exception as e:
        raise HTTPException(502, f"Term structure failed: {e}")


@app.get("/api/fno/options/greeks-surface/{symbol}")
def options_greeks_surface(symbol: str, expiry: str | None = None):
    """Full Greeks surface for all strikes in an expiry."""
    try:
        sym = symbol.upper()
        q = yf_prov.quote(sym.upper())
        spot = q.get("ltp") or q.get("prev_close", 0)
        
        chain = nse.option_chain(sym, expiry)
        if chain.empty:
            raise HTTPException(404, "No chain data")
        
        chain_iv = iv_surface(chain, spot)
        results = []
        for _, row in chain_iv.iterrows():
            if row.get("ce_iv", 0) > 0:
                T = row.get("dte", 30) / 365.0
                g = full_greeks(spot, row["strike"], T, settings.RISK_FREE_RATE, 
                               row["ce_iv"]/100, "CE")
                results.append({"strike": row["strike"], "type": "CE", **g.__dict__})
            if row.get("pe_iv", 0) > 0:
                T = row.get("dte", 30) / 365.0
                g = full_greeks(spot, row["strike"], T, settings.RISK_FREE_RATE, 
                               row["pe_iv"]/100, "PE")
                results.append({"strike": row["strike"], "type": "PE", **g.__dict__})
        
        return {"symbol": sym, "spot": spot, "expiry": chain["expiry"].iloc[0], 
                "greeks_surface": results}
    except Exception as e:
        raise HTTPException(502, f"Greeks surface failed: {e}")


@app.post("/api/fno/position-greeks")
def position_greeks_endpoint(positions: list[dict]):
    """Aggregate Greeks for a portfolio of options positions."""
    try:
        q = yf_prov.quote("NIFTY")
        spot = q.get("ltp") or 24500
        return position_greeks(positions, spot)
    except Exception as e:
        raise HTTPException(502, f"Position Greeks failed: {e}")


@app.post("/api/fno/delta-hedge")
def delta_hedge_endpoint(positions: list[dict]):
    """Calculate delta-neutral hedge for options portfolio."""
    try:
        q = yf_prov.quote("NIFTY")
        spot = q.get("ltp") or 24500
        return delta_neutral_hedge(positions, spot)
    except Exception as e:
        raise HTTPException(502, f"Delta hedge failed: {e}")


@app.post("/api/fno/scenario")
def scenario_analysis_endpoint(positions: list[dict], 
                                spot_shocks: list[float] = None,
                                vol_shocks: list[float] = None,
                                time_shocks: list[int] = None):
    """Scenario analysis for positions."""
    try:
        q = yf_prov.quote("NIFTY")
        spot = q.get("ltp") or 24500
        df = scenario_analysis(positions, spot, spot_shocks, vol_shocks, time_shocks)
        return {"scenarios": df.to_dict("records")}
    except Exception as e:
        raise HTTPException(502, f"Scenario analysis failed: {e}")


@app.get("/api/fno/alpha-beta/{symbol}")
def alpha_beta_endpoint(symbol: str, window: int = 252):
    """Rolling Alpha/Beta vs Nifty."""
    try:
        sym = symbol.upper()
        hist = yf_prov.history(sym, "2y")
        returns = hist["close"].pct_change().dropna()
        bench_hist = yf_prov.history("^NSEI", "2y")
        bench_returns = bench_hist["close"].pct_change().dropna()
        
        # Single period
        ab = capm_alpha_beta(returns, bench_returns)
        
        # Rolling
        rolling = rolling_alpha_beta(returns, bench_returns, window)
        
        return {
            "current": ab.__dict__,
            "rolling": rolling.tail(20).to_dict("records"),
        }
    except Exception as e:
        raise HTTPException(502, f"Alpha/Beta failed: {e}")


@app.get("/api/fno/futures/margin")
def futures_margin_endpoint(symbol: str, futures_price: float, lot_size: int = 50):
    """Futures margin estimate."""
    return futures_margin_estimate(futures_price, lot_size)


# =================================================================== #
# SPA
# =================================================================== #
