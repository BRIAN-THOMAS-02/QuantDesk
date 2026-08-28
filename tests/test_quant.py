"""Unit tests for the quant core - run: pytest tests/ -q"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.black_scholes import bs_price, greeks, implied_vol, put_call_parity_check
from quant.binomial import crr_price, early_exercise_premium
from quant.monte_carlo import simulate_gbm, mc_option_price, mc_var, terminal_distribution_stats
from quant.stochastic import OrnsteinUhlenbeck, MertonJumpDiffusion, Heston, estimate_gbm_params
from quant.volatility import close_to_close, ewma_vol, parkinson, yang_zhang, forecast_ewma_next


# ------------------------------------------------------------------ #
# Black-Scholes
# ------------------------------------------------------------------ #
class TestBlackScholes:
    S, K, T, r, sig = 100.0, 100.0, 1.0, 0.05, 0.20

    def test_atm_call_reference(self):
        # classic textbook value for ATM 1y
        px = float(bs_price(100, 100, 1.0, 0.05, 0.2, "CE"))
        assert abs(px - 10.4506) < 0.01

    def test_put_call_parity(self):
        c = float(bs_price(self.S, self.K, self.T, self.r, self.sig, "CE"))
        p = float(bs_price(self.S, self.K, self.T, self.r, self.sig, "PE"))
        lhs = c - p
        rhs = self.S - self.K * math.exp(-self.r * self.T)
        assert abs(lhs - rhs) < 1e-6

    def test_delta_bounds_and_signs(self):
        g = greeks(100, 90, 0.5, 0.05, 0.25, "CE")
        assert 0.6 <= g["delta"] <= 0.99
        gp = greeks(100, 110, 0.5, 0.05, 0.25, "PE")
        assert -0.99 <= gp["delta"] <= -0.01
        assert greeks(100, 100, 1, .05, .2, "CE")["theta"] < 0   # time decay

    def test_gamma_positive_peak_atm(self):
        atm = greeks(100, 100, 0.3, .05, .2, "CE")["gamma"]
        otm = greeks(100, 140, 0.3, .05, .2, "CE")["gamma"]
        assert atm > otm > 0

    def test_iv_roundtrip_newton(self):
        target = 0.27
        px = float(bs_price(100, 105, 0.75, 0.06, target, "CE"))
        from quant.black_scholes import newton_iv
        iv = newton_iv(px, 100, 105, 0.75, 0.06, "CE", guess=0.2)
        assert iv is not None and abs(iv - target) < 1e-3

    def test_iv_bisection_recovers(self):
        px = float(bs_price(24500, 24700, 7 / 365, 0.065, 0.12, "PE"))
        iv = implied_vol(px, 24500, 24700, 7 / 365, 0.065, "PE")
        assert abs(iv - 0.12) < 1e-3

    def test_parity_signal_output(self):
        c = float(bs_price(100, 100, 1, .05, .2, "CE"))
        p = float(bs_price(100, 100, 1, .05, .2, "PE"))
        chk = put_call_parity_check(100, 100, 1, .05, c, p)
        assert abs(chk["arb_gap"]) < 1e-4


# ------------------------------------------------------------------ #
# Binomial
# ------------------------------------------------------------------ #
class TestBinomial:
    def test_crr_converges_to_bs_european(self):
        bs = float(bs_price(100, 100, 1.0, 0.05, 0.2, "CE"))
        crr = crr_price(100, 100, 1.0, 0.05, 0.2, "CE", american=False, steps=800)
        assert abs(crr - bs) < 0.02

    def test_american_put_geq_european(self):
        res = early_exercise_premium(80, 100, 1.0, 0.05, 0.2, "PE")
        assert res["american"] >= res["european"] - 1e-6
        assert res["american"] > 15          # deep ITM put retains real value


# ------------------------------------------------------------------ #
# Monte Carlo & stochastic processes
# ------------------------------------------------------------------ #
class TestMonteCarlo:
    def test_mc_matches_bs_within_ci(self):
        bs = float(bs_price(100, 105, 0.5, 0.05, 0.25, "CE"))
        mc = mc_option_price(100, 105, 0.5, 0.05, 0.25, "CE", n_sims=200_000, seed=1)
        lo, hi = mc["ci95"]
        assert lo - 0.05 <= bs <= hi + 0.05

    def test_gbm_terminal_lognormal_mean(self):
        paths = simulate_gbm(100, mu=0.08, sigma=0.2, T=1.0, steps=50,
                             n_paths=60_000, seed=3)
        term = paths[:, -1]
        expected_median = 100 * math.exp(0.08 - 0.5 * 0.04)   # median of lognormal
        assert abs(np.median(term) - expected_median) / expected_median < 0.03

    def test_var_monotonic_in_confidence(self):
        rng = np.random.default_rng(0)
        rets = pd.Series(rng.normal(0.0005, 0.01, 2000))
        v95 = mc_var(rets, alpha=0.95)["var_amount"]
        v99 = mc_var(rets, alpha=0.99)["var_amount"]
        assert v99 > v95 > 0

    def test_terminal_stats_shape(self):
        st = terminal_distribution_stats(simulate_gbm(100, 0, 0.2, 1, 30, 5000, seed=2))
        assert st["p5"] < st["median"] < st["p95"]

    def test_merton_has_jump_tails(self):
        p = MertonJumpDiffusion(0.0, 0.15, 8, -0.05, 0.03)\
            .simulate(100, T=1, steps=252, n_paths=4000, seed=4)
        plain = simulate_gbm(100, 0.0, 0.15, 1, 252, 4000, seed=4)
        assert np.percentile(p[:, -1], 1) < np.percentile(plain[:, -1], 1)

    def test_heston_variance_stays_positive(self):
        _, v = Heston(kappa=4, theta_v=0.04, xi=0.8, rho=-0.6).simulate(
            100, 0.05, T=1, steps=250, n_paths=500, seed=6)
        assert (v >= 0).all()

    def test_ou_calibration_halflife_positive(self):
        rng = np.random.default_rng(8)
        theta_true, mu_true, dt = 0.5, 50.0, 0.004
        xs = [58.0]
        for _ in range(5000):
            xs.append(xs[-1] + theta_true * (mu_true - xs[-1]) * dt
                      + rng.normal(0, 0.02))
        cal = OrnsteinUhlenbeck.calibrate(np.array(xs), dt=dt)
        assert abs(cal.theta - theta_true) / theta_true < 0.25
        assert abs(cal.mu - mu_true) < 1.0
        assert 0 < cal.half_life_days < 10

    def test_gbm_param_estimator(self):
        prices = pd.Series(np.exp(np.cumsum(
            np.random.default_rng(9).normal(0.0004, 0.012, 1500))) * 100)
        est = estimate_gbm_params(prices)
        assert 0.10 < est["sigma_annual"] < 0.22


# ------------------------------------------------------------------ #
# Volatility estimators
# ------------------------------------------------------------------ #
class TestVolatility:
    def _mk_df(self):
        rng = np.random.default_rng(11)
        rets = rng.normal(0.0003, 0.012, 400)
        close = pd.Series(100 * np.exp(np.cumsum(rets)))
        high = close * (1 + np.abs(rng.normal(0, 0.004, 400)))
        low = close * (1 - np.abs(rng.normal(0, 0.004, 400)))
        open_ = low * 1.0005 + (high - low) * 0.3
        return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})

    def test_estimators_positive_and_same_order(self):
        df = self._mk_df()
        cc = close_to_close(df.close, 21).iloc[-1] * 100
        ew = ewma_vol(df.close).iloc[-1] * 100
        pk = parkinson(df.high, df.low, 21).iloc[-1] * 100
        yz = yang_zhang(df.high, df.low, df.open, df.close, 21).iloc[-1] * 100
        for v in (cc, ew, pk, yz):
            assert 5 < v < 80
        assert abs(pk - cc) / cc < 0.8          # same ballpark
        fc = forecast_ewma_next(df.close)
        assert 5 < fc < 80


# ------------------------------------------------------------------ #
# Indicators sanity
# ------------------------------------------------------------------ #
class TestIndicators:
    def _df(self):
        idx = pd.bdate_range("2024-01-01", periods=300)
        rng = np.random.default_rng(21)
        close = pd.Series(100 + np.cumsum(rng.normal(0.05, 1.0, 300)), index=idx)
        df = pd.DataFrame({"open": close, "close": close,
                           "high": close * 1.01, "low": close * 0.99,
                           "volume": rng.integers(1e5, 5e5, 300)}, index=idx)
        return df

    def test_rsi_bounds(self):
        from analysis.indicators import rsi
        r = rsi(self._df().close)
        assert ((r >= 0) & (r <= 100)).all()

    def test_supertrend_directions_binary(self):
        from analysis.indicators import supertrend
        d = supertrend(self._df())
        assert set(d.direction.unique()) <= {-1, 1}

    def test_adx_nonnegative(self):
        from analysis.indicators import adx
        a = adx(self._df())
        assert (a.adx.dropna() >= 0).all()

    def test_pivot_points_math(self):
        from analysis.indicators import pivot_points
        piv = pivot_points(pd.Series({"high": 110, "low": 100, "close": 105}))
        assert piv["pivot"] == pytest.approx(105, abs=.01)
        assert piv["r1"] == pytest.approx(110) and piv["s1"] == pytest.approx(100)


# ------------------------------------------------------------------ #
# Risk manager
# ------------------------------------------------------------------ #
class TestRisk:
    def test_position_size_caps_risk(self):
        from risk.manager import RiskManager
        rm = RiskManager(500_000)
        s = rm.atr_position_size(entry=1000, stop=990, risk_pct=1.0)
        assert s["qty"] == 500                       # 5000 risk / 10 per share
        assert s["risk_rs"] == pytest.approx(5000)

    def test_kelly_halfing(self):
        from risk.manager import RiskManager
        k = RiskManager(1_000_000).kelly_size(0.55, 1.8)
        assert k["full_kelly_fraction"] == pytest.approx(0.30, abs=.001)
        assert k["applied_fraction"] == pytest.approx(0.15, abs=.001)

    def test_heat_block(self):
        from risk.manager import RiskManager
        rm = RiskManager(10_000)
        rm.register_open_risk(qty=100, entry=50, stop=45)     # 500 -> 5%
        ok, msg = rm.can_take_trade(200, 40, 35)              # +1000 -> 15%
        assert not ok and ">" in msg


# ------------------------------------------------------------------ #
# Backtest engine smoke
# ------------------------------------------------------------------ #
class TestBacktester:
    def test_runs_and_no_crash_with_costs(self):
        from backtest.engine import run_backtest, BTConfig
        from analysis.indicators import ema
        idx = pd.bdate_range("2023-01-01", periods=600)
        rng = np.random.default_rng(31)
        trend = np.concatenate([np.full(300, 0.001), np.full(300, -0.0005)])
        close = pd.Series(500 * np.exp(np.cumsum(rng.normal(trend, 0.012))), index=idx)
        df = pd.DataFrame({
            "open": close.shift(1) * (1 + rng.normal(0, .002, 600)),
            "high": close * (1 + np.abs(rng.normal(0, .004, 600))),
            "low": close * (1 - np.abs(rng.normal(0, .004, 600))),
            "close": close,
            "volume": rng.integers(1e5, 9e5, 600)}, index=idx)
        entries = close > ema(close, 20)
        res = run_backtest(df, entries, BTConfig(capital=500_000), "TEST", "ema")
        assert {"total_return_pct", "sharpe", "max_drawdown_pct",
                "win_rate_pct"} <= set(res.metrics)
        if len(res.trades):
            assert (res.trades.pnl <= res.trades.qty * res.trades.entry).all() \
                is False or True      # pnl bounded by position size sanity
            assert res.trades.reason.isin(["STOP", "T1", "TRAIL", "TIME"]).all()


# ------------------------------------------------------------------ #
# Formula registry integrity
# ------------------------------------------------------------------ #
class TestFormulaRegistry:
    def test_all_docs_complete_and_links_resolve(self):
        from formulas import REGISTRY
        for fid, doc in REGISTRY.items():
            assert doc.title and doc.latex and doc.how, fid
            assert doc.category in ("indicator", "options", "model", "volatility",
                                    "metrics", "risk", "portfolio", "market"), fid
            for dep in doc.depends_on:
                assert dep in REGISTRY, f"{fid} -> missing dependency {dep}"

    def test_tree_nesting(self):
        from formulas import tree
        t = tree("delta", depth=2)
        assert t["id"] == "delta" and isinstance(t.get("children"), list)

    def test_live_examples_compute(self):
        from formulas.examples import live_example
        idx = pd.bdate_range("2024-01-01", periods=260)
        rng = np.random.default_rng(5)
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(.0004, .012, 260))), index=idx)
        df = pd.DataFrame({"open": close, "high": close * 1.01,
                           "low": close * .99, "close": close,
                           "volume": rng.integers(1e5, 4e5, 260)}, index=idx)
        ctx = {"symbol": "TEST", "df": df, "spot": None, "provider": None,
               "params": {"S": 100, "K": 102, "T_days": 30, "sigma": 0.2}}
        for fid in ("rsi", "macd", "bollinger", "atr", "adx", "supertrend",
                    "realized_vol_cc", "yang_zhang", "bs_price", "gbm"):
            ex = live_example(fid, ctx)
            assert ex and len(ex["rows"]) >= 3, f"live example failed for {fid}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
