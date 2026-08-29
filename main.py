"""QuantDesk India — command line interface.

  python main.py serve                 # launch web dashboard (http://localhost:8080)
  python main.py quote RELIANCE
  python main.py screener --top 12
  python main.py signal RELIANCE --strategy supertrend_rsi
  python main.py backtest RELIANCE --strategy breakout_pullback
  python main.py fiidii                # institutional flows + regime
  python main.py whales --days 3
  python main.py chain NIFTY           # option chain + PCR/max pain
  python main.py options iron_condor --spot 24500
  python main.py bs --spot 24500 --strike 24600 --days 7 --sigma 14
  python main.py vol RELIANCE          # volatility estimators + cone
  python main.py simulate RELIANCE --model heston
  python main.py optimize RELIANCE,TCS,HDFCBANK
  python main.py size --entry 2500 --stop 2440
  python main.py formula rsi           # explain any calculation (+live example)
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from config import settings                      # noqa: E402
from utils.helpers import pretty_table            # noqa: E402


def out(x):
    if isinstance(x, pd.DataFrame):
        print(pretty_table(x) if not x.empty else "(empty)")
    elif isinstance(x, dict):
        print(json.dumps(x, indent=2, default=str))
    else:
        print(x)


def cmd_quote(a):
    from data.providers.yfinance_provider import YFinanceProvider
    q = YFinanceProvider().quote(a.symbol)
    f = YFinanceProvider().fundamentals(a.symbol)
    out({**q, **{k: v for k, v in f.items()}})


def cmd_screener(a):
    from analysis.screener import Screener
    sc = Screener(universe=a.universe.split(",") if a.universe else None)
    res = sc.run(top_n=a.top, refresh=True)
    cols = [c for c in ("symbol", "close", "rsi", "adx", "st_dir", "ret_3m_pct",
                        "rs_vs_nifty_pct", "vol_z", "pct_from_52wh", "score") if c in res]
    out(res[cols])


def cmd_signal(a):
    from strategies.swing import SWING_STRATEGIES
    from strategies.intraday import INTRADAY_STRATEGIES
    from data.providers.yfinance_provider import YFinanceProvider
    cls = SWING_STRATEGIES.get(a.strategy) or INTRADAY_STRATEGIES.get(a.strategy)
    if not cls:
        sys.exit(f"unknown strategy {a.strategy}")
    strat = cls(); strat.symbol = a.symbol.upper()
    df = YFinanceProvider().history(strat.symbol, "1y")
    sig = strat.generate(df).as_dict()
    if sig["direction"] == 1 and sig.get("stop"):
        from risk.manager import RiskManager
        sig["sizing"] = RiskManager(settings.CAPITAL).atr_position_size(
            sig["entry"], sig["stop"])
    out(sig)


def cmd_backtest(a):
    from strategies.swing import SWING_STRATEGIES
    from data.providers.yfinance_provider import YFinanceProvider
    from backtest.engine import run_backtest, BTConfig
    cls = SWING_STRATEGIES[a.strategy]
    df = YFinanceProvider().history(a.symbol, a.period)
    cfg = BTConfig(capital=a.capital, risk_pct=a.risk, atr_mult_stop=a.atr_mult,
                   max_hold_days=a.hold)
    res = run_backtest(df, cls().entries(df), cfg, a.symbol.upper(), a.strategy)
    out(res.metrics)
    if res.trades is not None and len(res.trades):
        print("\nlast trades:")
        out(res.trades.tail(8))


def cmd_fiidii(_a):
    from data.osint.fii_dii import FiiDiiTracker
    t = FiiDiiTracker()
    print(t.summary_text())
    out("\nregime: " + json.dumps(t.regime_bias(), default=str))


def cmd_whales(a):
    from data.osint.whale_tracker import WhaleTracker
    wt = WhaleTracker()
    t = wt.whale_table(days=a.days)
    if t.empty:
        print("no deal prints available right now (NSE may be blocking)")
    else:
        cols = [c for c in ("date", "deal_type", "symbol", "client", "class",
                            "side", "qty", "avg_price", "value_cr") if c in t]
        out(t[cols].head(30))


def cmd_chain(a):
    from data.providers.nse_provider import NSEProvider
    from quant.black_scholes import greek_chain
    from strategies.options_strategy import oi_intelligence
    nse = NSEProvider()
    ch = nse.option_chain(a.underlying, a.expiry)
    dte = max((pd.to_datetime(ch.expiry.iloc[0], format="%d-%b-%Y")
               - pd.Timestamp.now()).days, 0) if len(ch) else 7
    ch = greek_chain(ch, days_to_expiry=dte)
    spot = ch.spot.iloc[0]
    near = ch[(ch.strike - spot).abs() <= spot * 0.03]
    cols = ["strike", "ce_oi", "ce_iv", "ce_bs", "ce_delta", "pe_oi", "pe_iv", "pe_delta"]
    out(near[[c for c in cols if c in near]])
    print("\nintelligence:")
    out(oi_intelligence(ch))


def cmd_options(a):
    from strategies.options_strategy import OptionsStrategyEngine
    eng = OptionsStrategyEngine(spot=a.spot)
    fn = getattr(eng, {"iron_condor": "iron_condor", "bull_call_spread": "bull_call_spread",
                       "covered_call": "covered_call", "csp": "cash_secured_put",
                       "straddle": "straddle_analysis"}[a.preset])
    st = fn(sigma_s=a.sigma / 100, days=a.days)
    print(st["label"])
    print(f"net premium {st['net_premium']} | max profit {st['max_profit']} | "
          f"max loss {st['max_loss']} | breakevens {st['breakevens']}")


def cmd_bs(a):
    from quant.black_scholes import bs_price, greeks
    T = a.days / 365; S = a.spot
    for kind in ("CE", "PE"):
        p = bs_price(S, a.strike, T, settings.RISK_FREE_RATE, a.sigma / 100, kind)
        g = greeks(S, a.strike, T, settings.RISK_FREE_RATE, a.sigma / 100, kind)
        print(kind, f"px={p:.2f}", g)


def cmd_vol(a):
    from data.providers.yfinance_provider import YFinanceProvider
    from quant.volatility import (vol_cone, close_to_close, ewma_vol, parkinson,
                                  garman_klass, yang_zhang, forecast_ewma_next,
                                  atr_percentile)
    df = YFinanceProvider().history(a.symbol, "2y")
    print("estimators (21d annualized %):")
    print(f"  close-close : {close_to_close(df.close, 21).iloc[-1]*100:.2f}")
    print(f"  EWMA        : {ewma_vol(df.close).iloc[-1]*100:.2f}")
    print(f"  Parkinson   : {parkinson(df.high, df.low, 21).iloc[-1]*100:.2f}")
    print(f"  Garman-Klass: {garman_klass(df.high,df.low,df.open,df.close,21).iloc[-1]*100:.2f}")
    print(f"  Yang-Zhang  : {yang_zhang(df.high,df.low,df.open,df.close,21).iloc[-1]*100:.2f}")
    print(f"  next-day EWMA forecast: {forecast_ewma_next(df.close)}%")
    print(f"  ATR percentile regime : {atr_percentile(df.high, df.low, df.close)}")
    print("\nvol cone:")
    out(vol_cone(df.close))


def cmd_simulate(a):
    from data.providers.yfinance_provider import YFinanceProvider
    from quant.monte_carlo import simulate_gbm, terminal_distribution_stats
    from quant.stochastic import MertonJumpDiffusion, Heston, estimate_gbm_params
    df = YFinanceProvider().history(a.symbol, "2y")
    cal = estimate_gbm_params(df.close); S0 = float(df.close.iloc[-1])
    mu, sg = cal["mu_annual"], cal["sigma_annual"]
    T = a.days / 252
    if a.model == "merton":
        paths = MertonJumpDiffusion(mu, sg, a.jumps, -0.03, 0.05)\
            .simulate(S0, T=T, steps=a.days, n_paths=a.paths, seed=5)
    elif a.model == "heston":
        paths, _ = Heston(kappa=5, theta_v=sg**2, xi=0.9, rho=-0.7)\
            .simulate(S0, mu, T=T, steps=a.days, n_paths=a.paths, seed=7)
    else:
        paths = simulate_gbm(S0, mu, sg, T=T, steps=a.days, n_paths=a.paths, seed=42)
    stats = terminal_distribution_stats(paths[:, ::max(a.days // 60, 1)])
    out({"model": a.model, "calibration": cal, "S0": round(S0), **stats})


def cmd_optimize(a):
    from data.providers.yfinance_provider import YFinanceProvider
    from analysis.portfolio_opt import PortfolioOptimizer
    syms = [s.strip().upper() for s in a.symbols.split(",")]
    prices = pd.DataFrame({s: YFinanceProvider().history(s, "2y").close for s in syms}).dropna()
    opt = PortfolioOptimizer(prices)
    out(opt.summary())


def cmd_size(a):
    from risk.manager import RiskManager
    rm = RiskManager(a.capital)
    out(rm.atr_position_size(a.entry, a.stop, a.risk))


def cmd_formula(a):
    from formulas import get_doc, live_example, tree
    doc = get_doc(a.fid)
    if not doc:
        sys.exit("unknown formula id. try: python main.py formulas")
    payload = tree(a.fid, depth=1)
    try:
        from webapp.server import ctx_for
        payload["live_example"] = live_example(a.fid, ctx_for(a.symbol))
    except Exception:
        pass
    out(payload)


def cmd_formulas(_a):
    from formulas import REGISTRY, CATEGORIES
    rows = [{"category": CATEGORIES[d.category], "id": d.id, "title": d.title}
            for d in REGISTRY.values()]
    out(pd.DataFrame(rows))


def cmd_serve(a):
    import uvicorn
    uvicorn.run("webapp.server:app", host=a.host, port=a.port, reload=False)


def main():
    p = argparse.ArgumentParser(description="QuantDesk India")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve"); s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080); s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("quote"); s.add_argument("symbol"); s.set_defaults(fn=cmd_quote)

    s = sub.add_parser("screener"); s.add_argument("--top", type=int, default=12)
    s.add_argument("--universe", default=None); s.set_defaults(fn=cmd_screener)

    s = sub.add_parser("signal"); s.add_argument("symbol")
    s.add_argument("--strategy", default="supertrend_rsi"); s.set_defaults(fn=cmd_signal)

    s = sub.add_parser("backtest"); s.add_argument("symbol")
    s.add_argument("--strategy", default="supertrend_rsi")
    s.add_argument("--period", default="2y"); s.add_argument("--capital", type=float, default=settings.CAPITAL)
    s.add_argument("--risk", type=float, default=settings.RISK_PER_TRADE_PCT)
    s.add_argument("--atr-mult", type=float, default=2.0)
    s.add_argument("--hold", type=int, default=20); s.set_defaults(fn=cmd_backtest)

    sub.add_parser("fiidii").set_defaults(fn=cmd_fiidii)
    s = sub.add_parser("whales"); s.add_argument("--days", type=int, default=3)
    s.set_defaults(fn=cmd_whales)

    s = sub.add_parser("chain"); s.add_argument("underlying", nargs="?", default="NIFTY")
    s.add_argument("--expiry", default=None); s.set_defaults(fn=cmd_chain)

    s = sub.add_parser("options"); s.add_argument("preset",
        choices=["iron_condor", "bull_call_spread", "covered_call", "csp", "straddle"])
    s.add_argument("--spot", type=float, required=True)
    s.add_argument("--sigma", type=float, default=15)
    s.add_argument("--days", type=int, default=21); s.set_defaults(fn=cmd_options)

    s = sub.add_parser("bs"); s.add_argument("--spot", type=float, required=True)
    s.add_argument("--strike", type=float, required=True)
    s.add_argument("--days", type=float, default=7); s.add_argument("--sigma", type=float, default=15)
    s.set_defaults(fn=cmd_bs)

    s = sub.add_parser("vol"); s.add_argument("symbol"); s.set_defaults(fn=cmd_vol)

    s = sub.add_parser("simulate"); s.add_argument("symbol")
    s.add_argument("--model", choices=["gbm", "merton", "heston"], default="gbm")
    s.add_argument("--days", type=int, default=126); s.add_argument("--paths", type=int, default=3000)
    s.add_argument("--jumps", type=float, default=4.0); s.set_defaults(fn=cmd_simulate)

    s = sub.add_parser("optimize"); s.add_argument("symbols"); s.set_defaults(fn=cmd_optimize)

    s = sub.add_parser("size"); s.add_argument("--entry", type=float, required=True)
    s.add_argument("--stop", type=float, required=True)
    s.add_argument("--capital", type=float, default=settings.CAPITAL)
    s.add_argument("--risk", type=float, default=settings.RISK_PER_TRADE_PCT)
    s.set_defaults(fn=cmd_size)

    sub.add_parser("formulas").set_defaults(fn=cmd_formulas)
    s = sub.add_parser("formula"); s.add_argument("fid")
    s.add_argument("--symbol", default="RELIANCE"); s.set_defaults(fn=cmd_formula)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
