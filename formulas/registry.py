"""Central formula documentation registry.

Schema per entry:
  id, title, category, latex (KaTeX), text_formula (ASCII),
  what (why trader cares), how (numbered computation recipe),
  inputs {name: meaning}, depends_on [nested formula ids -> cascade view],
  interpretation (thresholds/trading read), static_example (worked numbers).
Live dynamic examples live in examples.py keyed by same ids.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FormulaDoc:
    id: str
    title: str
    category: str
    latex: str | list[str]
    text_formula: str
    what: str
    how: list[str]
    inputs: dict[str, str] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    interpretation: str = ""
    static_example: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


CATEGORIES = {
    "indicator": "Technical Indicators",
    "options": "Options / Black-Scholes",
    "model": "Stochastic & Simulation Models",
    "volatility": "Volatility Estimators",
    "metrics": "Backtest Metrics",
    "risk": "Risk & Position Sizing",
    "portfolio": "Portfolio Optimization",
    "market": "Market Intelligence (FII/DII/Whales)",
}

REGISTRY: dict[str, FormulaDoc] = {}


def _add(doc: FormulaDoc):
    REGISTRY[doc.id] = doc


def get_doc(fid: str) -> FormulaDoc | None:
    return REGISTRY.get(fid)


def list_ids() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fid, doc in REGISTRY.items():
        out.setdefault(doc.category, []).append(fid)
    return out


def tree(fid: str, depth: int = 2, _seen: set | None = None) -> dict:
    """Embed a formula plus its dependency docs recursively -> cascade view."""
    seen = _seen if _seen is not None else set()
    doc = get_doc(fid)
    if doc is None or fid in seen or depth < 0:
        return {"missing": True, "id": fid}
    seen.add(fid)
    d = doc.to_dict()
    d["children"] = [tree(c, depth - 1, seen) for c in doc.depends_on
                     if c in REGISTRY]
    return d


# ===================================================================== #
# TECHNICAL INDICATORS
# ===================================================================== #
_add(FormulaDoc(
    id="sma", title="Simple Moving Average", category="indicator",
    latex=r"SMA_n(t)=\frac{1}{n}\sum_{i=0}^{n-1} P_{t-i}",
    text_formula="SMA(n) = mean of last n closes",
    what="Smooths price to reveal trend direction; dynamic support/resistance.",
    how=["Take the last n closing prices", "Sum them", "Divide by n"],
    inputs={"n": "lookback period (e.g. 50, 200)"},
    interpretation="Price above rising SMA200 = long-term uptrend. Golden cross: SMA50>SMA200.",
    static_example={"closes(last 5)": "[1010, 1008, 1012, 1015, 1020]", "n": 5,
                    "SMA5": "(1010+1008+1012+1015+1020)/5 = 1013.0"}))

_add(FormulaDoc(
    id="ema", title="Exponential Moving Average", category="indicator",
    latex=r"EMA_t=\alpha P_t+(1-\alpha)\,EMA_{t-1},\quad \alpha=\frac{2}{n+1}",
    text_formula="EMA_t = alpha*P_t + (1-alpha)*EMA_{t-1}, alpha=2/(n+1)",
    what="Weights recent prices more than SMA - reacts faster to reversals.",
    how=["Compute alpha = 2/(n+1)", "Seed EMA_0 = first close (or SMA)",
         "Recursively apply the update each bar"],
    inputs={"n": "span (e.g. 20/50/200)"}, depends_on=["sma"],
    interpretation="EMA20>EMA50 = short-term momentum up. Used as trailing stop line.",
    static_example={"P_t": "1020", "EMA_prev": "1010", "n": 20,
                    "alpha": "2/21 = 0.0952", "EMA_t": "0.0952*1020 + 0.9048*1010 = 1010.95"}))

_add(FormulaDoc(
    id="rsi", title="Relative Strength Index (Wilder)", category="indicator",
    latex=[r"\text{Gain}_t=\max(\Delta P_t,0),\ \ \text{Loss}_t=\max(-\Delta P_t,0)",
           r"\bar{G}_t=\frac{(n-1)\bar{G}_{t-1}+\text{Gain}_t}{n}\quad\text{(Wilder smoothing)}",
           r"RS=\frac{\bar{G}_t}{\bar{L}_t},\qquad RSI=100-\frac{100}{1+RS}"],
    text_formula="avg gain/loss via Wilder EMA(alpha=1/n); RS=avgGain/avgLoss; RSI=100-100/(1+RS)",
    what="Momentum oscillator 0-100 measuring speed of recent gains vs losses.",
    how=["Compute daily change ΔP", "Split into gains & losses",
         "Smooth both with Wilder EMA over n=14", "RS = avgGain/avgLoss",
         "RSI = 100 - 100/(1+RS)"],
    inputs={"ΔP": "close-to-close change", "n": "period (default 14)"},
    depends_on=["ema"],
    interpretation="<30 oversold (mean-reversion buys), >70 overbought, 50-70 = healthy uptrend pullback zone. Divergence with price = reversal warning.",
    static_example={"avg_gain(14)": "4.2", "avg_loss(14)": "1.4", "RS": "4.2/1.4 = 3.0",
                    "RSI": "100 - 100/4 = 75.0"}))

_add(FormulaDoc(
    id="macd", title="MACD (Moving Average Convergence Divergence)", category="indicator",
    latex=[r"\text{MACD}=EMA_{12}-EMA_{26}", r"\text{Signal}=EMA_9(\text{MACD})",
           r"\text{Histogram}=\text{MACD}-\text{Signal}"],
    text_formula="MACD=EMA12-EMA26; Signal=EMA9(MACD); Hist=MACD-Signal",
    what="Trend + momentum combo; crossovers time entries, histogram measures acceleration.",
    how=["Compute EMA12 & EMA26 of close", "Subtract -> MACD line",
         "EMA9 of MACD -> Signal line", "Difference -> Histogram"],
    inputs={"fast/slow/signal": "12/26/9 standard"},
    depends_on=["ema"],
    interpretation="Bullish cross (MACD crosses above signal) below zero = strong early trend. Rising histogram = momentum building."))

_add(FormulaDoc(
    id="atr", title="Average True Range (ATR)", category="indicator",
    latex=[r"TR_t=\max(H-L,\ |H-C_{t-1}|,\ |L-C_{t-1}|)",
           r"ATR_t=\frac{(n-1)ATR_{t-1}+TR_t}{n}\ \text{(Wilder smoothing)}"],
    text_formula="TR=max(H-L,|H-Cp|,|L-Cp|); ATR=Wilder-smoothed TR over n",
    what="True volatility in ₹ terms - the backbone of stops, targets & position size.",
    how=["For each bar compute True Range (gaps included via prev close)",
         "Smooth TR with Wilder EMA over n=14"],
    inputs={"H,L,C": "high/low/close", "n": "14 default"},
    depends_on=["ema"],
    interpretation="Stop = entry -/+ 2×ATR. ATR>3% of price = wide swings → reduce size. Use ATR percentile for regime awareness."))

_add(FormulaDoc(
    id="adx", title="ADX / Directional Movement (+DI, -DI)", category="indicator",
    latex=[r"+DM=\max(H-H_{t-1},0)\ \text{if}\ H-H_{t-1}>L_{t-1}-L\ \text{else }0",
           r"-DM=\max(L_{t-1}-L,0)\ \text{if}\ L_{t-1}-L>H-H_{t-1}\ \text{else }0",
           r"+DI=100\cdot\frac{Smooth(+DM)}{Smooth(TR)},\quad -DI\ \text{symmetric}",
           r"DX=100\cdot\frac{|+DI--DI|}{+DI+-DI},\quad ADX=Smooth(DX)"],
    text_formula="+DI/-DI from smoothed directional moves over smoothed TR; DX=100*|+DI - -DI|/(+DI+-DI); ADX=smooth(DX)",
    what="Measures TREND STRENGTH (not direction). The #1 filter separating trending from choppy regimes.",
    how=["Compute +DM/-DM between consecutive bars", "Smooth DMs and TR (Wilder, 14)",
         "+DI/-DI = 100×ratio", "DX from DI spread", "ADX = Wilder-smoothed DX"],
    inputs={"n": "14"},
    depends_on=["atr"],
    interpretation="ADX<20 choppy (mean-reversion only), 20-25 emerging trend, >25 strong trend (ride trend strategies), >40 mature trend (avoid fresh entries)."))

_add(FormulaDoc(
    id="bollinger", title="Bollinger Bands & %B", category="indicator",
    latex=[r"\text{Mid}_t=SMA_{20}(P),\quad \sigma=SMA_{20}\text{-stddev}",
           r"Upper=\text{Mid}+2\sigma,\quad Lower=\text{Mid}-2\sigma",
           r"\%B=\frac{P-Lower}{Upper-Lower},\quad BW=\frac{Upper-Lower}{\text{Mid}}\times100"],
    text_formula="Bands = SMA20 ± 2σ; %B=(P-Lower)/(Upper-Lower); Width=(U-L)/Mid*100",
    what="Volatility envelope around price; squeeze/expansion cycles time breakouts & reversion targets.",
    how=["20-period SMA = middle band", "Rolling std dev σ of same window",
         "Add/subtract 2σ for outer bands", "%B locates price inside bands"],
    inputs={"k": "2.0 std devs"},
    depends_on=["sma"],
    interpretation="%B<0 (below lower band) + RSI<32 = oversold reversion setup. Bandwidth at multi-month low = 'squeeze' → breakout imminent. Walking the upper band = strong trend."))

_add(FormulaDoc(
    id="supertrend", title="Supertrend", category="indicator",
    latex=[r"\text{BasicUB}=\frac{H+L}{2}+m\cdot ATR,\quad \text{BasicLB}=\frac{H+L}{2}-m\cdot ATR",
           r"FinalUB_t=\min(BasicUB_t, FinalUB_{t-1})\ \text{if}\ C_{t-1}>FinalUB_{t-1}",
           r"Direction flips when close crosses the opposite final band"],
    text_formula="Bands=(HL2)±mult*ATR with ratcheting (bands never loosen while trend holds); direction +1/-1 by which band price respects",
    what="Self-adjusting trailing stop system - THE most-used swing overlay on Indian charts.",
    how=["ATR(period=10)", "Build basic upper/lower bands around HL2 × multiplier 3",
         "Ratchet: final UB can only fall while trend up (and vice versa)",
         "Flip direction when close breaches opposite band"],
    inputs={"period": "10", "mult": "3.0"},
    depends_on=["atr"],
    interpretation="direction=+1 → hold longs with stop at supertrend line. Flip = exit/reverse. Works best daily/weekly on liquid NSE names."))

_add(FormulaDoc(
    id="donchian", title="Donchian Channel Breakout", category="indicator",
    latex=r"Upper_t=\max(H_{t-1..t-n}),\quad Lower_t=\min(L_{t-1..t-n})",
    text_formula="Upper=highest high of prior n bars (excl today); Lower=lowest low",
    what="Classic Turtle breakout levels - basis of the 20-day-high swing strategy.",
    how=["Rolling max of highs excluding current bar", "Same for lows"],
    inputs={"n": "20"},
    interpretation="Close > Upper20 on volume z>0.5 = valid breakout. Retest of level = low-risk re-entry."))

_add(FormulaDoc(
    id="vwap", title="VWAP (Volume Weighted Average Price)", category="indicator",
    latex=r"VWAP=\frac{\sum (\frac{H+L+C}{3})\cdot V}{\sum V}",
    text_formula="cumsum(typical_price * volume) / cumsum(volume), reset each session",
    what="Institutional fair-value benchmark - algos defend it intraday.",
    how=["Typical price TP=(H+L+C)/3 per bar", "Multiply by volume, cumsum through day",
         "Divide by cumulated volume", "Resets at each session open"],
    interpretation="Above VWAP = buyers control; dips to VWAP in uptrend = bounce entries. Below VWAP = sell rallies."))

_add(FormulaDoc(
    id="obv", title="On-Balance Volume", category="indicator",
    latex=r"OBV_t=OBV_{t-1}+\mathrm{sign}(\Delta C_t)\cdot V_t",
    what="Cumulative volume flow confirming price trends.",
    text_formula="OBV += sign(close_change)*volume",
    how=["If close up add volume, down subtract volume, unchanged skip",
         "Cumulate across history"],
    interpretation="Price new high without OBV new high = distribution (bearish divergence)."))

_add(FormulaDoc(
    id="mfi", title="Money Flow Index", category="indicator",
    latex=[r"TP=\frac{H+L+C}{3},\ MF=TP\times V",
           r"MFI=100-\frac{100}{1+\frac{\sum^{+}MF_{14}}{\sum^{-}MF_{14}}}"],
    text_formula="Positive/negative money flow split by TP rising/falling; ratio feeds RSI-style 0-100 scale",
    what="'Volume-weighted RSI' - catches accumulation/distribution RSI misses.",
    how=["Typical price TP=(H+L+C)/3", "Money flow MF = TP×volume",
         "Split into positive (TP up) & negative flows over 14 bars",
         "MFI = 100 − 100/(1 + posFlow/negFlow)"],
    inputs={"n": "14"},
    depends_on=["rsi"],
    interpretation="<20 oversold w/ volume confirmation, >80 overbought."))

_add(FormulaDoc(
    id="volume_zscore", title="Volume Z-Score", category="indicator",
    latex=r"z_t=\frac{V_t-\mu_{20}(V)}{\sigma_{20}(V)}",
    text_formula="z=(today volume - 20d mean)/20d stdev",
    what="Normalizes volume spikes - validates breakouts & whale activity.",
    how=["Mean & std of last 20 volumes", "(Today - mean)/std"],
    interpretation="z>2 = institutional-grade surge; breakout needs z>0.5 minimum. Negative z rallies are suspect."))

_add(FormulaDoc(
    id="fibonacci_levels", title="Fibonacci Retracements", category="indicator",
    latex=r"L_r = H - r\,(H-L),\quad r\in\{0.236,0.382,0.5,0.618,0.786\}",
    text_formula="Level = High - ratio*(High-Low) for uptrend retracements",
    what="Crowd-psychology support levels after an impulse leg.",
    how=["Identify swing high H and low L", "Multiply range by golden ratios",
         "Project down from H (uptrend)"],
    interpretation="0.382-0.618 confluence with EMA/pivot = high-probability bounce zones."))

_add(FormulaDoc(
    id="pivot_points_cpr", title="Floor Pivots + CPR", category="indicator",
    latex=[r"P=\frac{H+L+C}{3}", r"BC=\frac{H+L}{2},\ TC=2P-BC",
           r"R_1=2P-L,\ S_1=2P-H,\ R_2=P+(H-L),\ S_2=P-(H-L)"],
    text_formula="Pivot=(H+L+C)/3 from PREVIOUS day; CPR=[BC,TC]; R/S levels offset",
    what="Indian intraday staple - CPR width forecasts trend day vs range day.",
    how=["Take previous day H/L/C", "Compute pivot & central band (TC/BC)",
         "Project R1/R2/S1/S2"],
    interpretation="Narrow CPR (<0.25% width) = likely trending day (play ORB); wide CPR = fade extremes toward pivot."))

_add(FormulaDoc(
    id="relative_strength", title="Relative Strength vs Benchmark", category="indicator",
    latex=r"RS_{63}=\big(P_t/P_{t-63}\big)-\big(B_t/B_{t-63}\big)",
    text_formula="(stock 3m return) - (Nifty 3m return)",
    what="Cross-sectional outperformance - the core factor behind momentum portfolios.",
    how=["Compute stock 63d return", "Subtract benchmark (Nifty) 63d return"],
    interpretation="RS>+5% sustained = leadership candidate; negative RS in uptrend = laggard, avoid."))

_add(FormulaDoc(
    id="ichimoku", title="Ichimoku Cloud (Tenkan/Kijun/Kumo)", category="indicator",
    latex=[r"Tenkan=\frac{HH_9+LL_9}{2},\ Kijun=\frac{HH_{26}+LL_{26}}{2}",
           r"SenkouA=\frac{Tenkan+Kijun}{2}\ \text{(shifted 26 ahead)},\ SenkouB=\frac{HH_{52}+LL_{52}}{2}"],
    text_formula="Equilibrium midpoints of ranges; cloud projected forward 26 periods",
    what="All-in-one trend/momentum/support system popular for positional trades.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["donchian"],
    interpretation="Price above green cloud + Tenkan>Kijun = bullish regime; cloud twist = trend change warning."))

_add(FormulaDoc(
    id="williams_r", title="Williams %R", category="indicator",
    latex=r"\%R=-100\cdot\frac{HH_{14}-C}{HH_{14}-LL_{14}}",
    text_formula="-100*(highestHigh - Close)/(range14)",
    what="Fast stochastic-style oscillator (-100..0) for timing pullback entries.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["stochastic_kd"],
    interpretation=">-20 overbought, <-80 oversold; midline crossing up = momentum shift."))

_add(FormulaDoc(
    id="roc", title="Rate of Change", category="indicator",
    latex=r"ROC_n=\left(\frac{P_t}{P_{t-n}}-1\right)\times100",
    text_formula="percent change over n bars",
    what="Plain momentum measure feeding ranking systems.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["relative_strength"]))

_add(FormulaDoc(
    id="hma", title="Hull Moving Average", category="indicator",
    latex=r"HMA_n=EMA_{\sqrt{n}}\big(2\,EMA_{n/2}(P)-EMA_n(P)\big)",
    text_formula="EMA(sqrt(n)) applied to [2*EMA(n/2) - EMA(n)]",
    what="Near-zero-lag smooth MA for fast trend confirmation.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["ema"],
    interpretation="Slope flip of HMA16 = earliest trend-turn cue on hourly charts."))

_add(FormulaDoc(
    id="wma", title="Weighted Moving Average", category="indicator",
    latex=r"WMA_n=\frac{\sum_{i=1}^{n} i\cdot P_{t-n+i}}{n(n+1)/2}",
    text_formula="linear weights 1..n on last n closes",
    what="Linearly-weighted MA - intermediate between SMA and EMA responsiveness.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["ema"]))

_add(FormulaDoc(
    id="momentum_rank", title="6-2 Momentum Rank", category="indicator",
    latex=r"M_{6,2}=\frac{P_{t-126}}{P_{t-10}}-1",
    text_formula="return skipping most recent ~2 weeks (126 trading days lookback)",
    what="Academic cross-sectional momentum (skips short-term reversal noise).",
    how=["Price 126 sessions ago ÷ price 10 sessions ago", "Rank universe descending"],
    interpretation="Top decile M62 names held weekly = classic quant momentum book."))

_add(FormulaDoc(
    id="stochastic_kd", title="Stochastic Oscillator (%K/%D)", category="indicator",
    latex=[r"\%K=100\cdot SMA_3\!\Big(\frac{C-LL_{14}}{HH_{14}-LL_{14}}\Big)", r"\%D=SMA_3(\%K)"],
    text_formula="position of close inside 14-bar range, smoothed 3,3",
    what="Range-position oscillator for timing within trends.",
    how=["(Close - lowest low)/(range) ×100", "Smooth K by 3, D = SMA3(K)"],
    interpretation="%K>%D rising from <20 = buy timing in uptrends; avoid signals against ADX>25 trend."))

# ===================================================================== #
# OPTIONS / BLACK-SCHOLES
# ===================================================================== #
_add(FormulaDoc(
    id="bs_price", title="Black-Scholes-Merton Price", category="options",
    latex=[r"d_1=\frac{\ln(S/K)+(r-q+\sigma^2/2)T}{\sigma\sqrt{T}},\quad d_2=d_1-\sigma\sqrt{T}",
           r"C=Se^{-qT}N(d_1)-Ke^{-rT}N(d_2)",
           r"P=Ke^{-rT}N(-d_2)-Se^{-qT}N(-d_1)"],
    text_formula="d1=[ln(S/K)+(r-q+s^2/2)T]/(s*sqrt(T)); Call=S*N(d1)-K*e^-rT*N(d2); Put mirrored",
    what="Risk-neutral arbitrage-free option value - the pricing engine for every options strategy here.",
    how=["Compute moneyness ln(S/K)", "Add drift term (r-q+σ²/2)·T, divide by σ√T → d1",
         "d2 = d1 − σ√T", "Call = discounted expected payoff under risk-neutral measure",
         "Put via put-call parity mirror"],
    inputs={"S": "spot price", "K": "strike", "T": "time to expiry (years)",
            "r": "risk-free rate (~6.5% India)", "σ": "implied volatility (decimal)",
            "q": "dividend yield", "N(·)": "standard normal CDF"},
    depends_on=["d1_d2", "delta"],
    interpretation="Compare model vs market LTP: big gap ⇒ IV mispriced (see IV solver). Indian F&O: use T=days/365.",
    static_example={"S": 24500, "K": 24500, "T": "7/365", "σ": "12%", "r": "6.5%",
                    "result": "ATM call ≈ 24500*0.5*(σ√T/√(2π)) ≈ ₹92"}))
_add(FormulaDoc(
    id="d1_d2", title="d1 & d2 (Moneyness Terms)", category="options",
    latex=[r"d_1=\frac{\ln(S/K)+(r-q+\sigma^2/2)T}{\sigma\sqrt{T}}", r"d_2=d_1-\sigma\sqrt{T}"],
    text_formula="d1 = standardized log-moneyness incl. drift; d2 = probability-adjusted exercise distance",
    what="The two normal arguments driving every BS quantity; N(d1) = delta proxy, N(d2) = ITM probability proxy.",
    how=["log-moneyness ln(S/K) scaled by total vol σ√T",
         "shift by half variance + carry (r−q)"],
    depends_on=["bs_price"],
    interpretation="d1≈0 ATM; |d1|>1 deep ITM/OTM where greeks saturate."))

_add(FormulaDoc(
    id="delta", title="Delta (∂V/∂S) & Greek Suite", category="options",
    latex=[r"\Delta_C=e^{-qT}N(d_1),\quad \Delta_P=-e^{-qT}N(-d_1)",
           r"\Gamma=\frac{e^{-qT}\phi(d_1)}{S\sigma\sqrt{T}}",
           r"\Theta_C=\frac{-S e^{-qT}\phi(d_1)\sigma}{2\sqrt{T}}-rKe^{-rT}N(d_2)+qSe^{-qT}N(d_1)",
           r"Vega=S e^{-qT}\phi(d_1)\sqrt{T},\quad \rho_C=KTe^{-rT}N(d_2)"],
    text_formula="Delta=rate of change vs spot; Gamma=rate of change of delta; Theta=time decay/day; Vega=pnl per 1 vol pt; Rho=rate sensitivity",
    what="Risk dashboard of any option position: direction (Δ), convexity (Γ), bleed (Θ), vol sensitivity (ν).",
    how=["Differentiate BS price w.r.t. each parameter analytically",
         "Theta reported per calendar day (/365)", "Vega per 1 vol point (/100)"],
    inputs={"φ(·)": "standard normal pdf"},
    depends_on=["d1_d2", "bs_price"],
    interpretation="Long options = +Γ −Θ (pay for movement); short = −Γ +Θ (collect decay, tail risk). ATM weekly Nifty Θ ≈ −₹13/day per lot near expiry."))

_add(FormulaDoc(
    id="gamma", title="Gamma (∂²V/∂S²)", category="options",
    latex=r"\Gamma=\frac{\phi(d_1)}{S\sigma\sqrt{T}}",
    text_formula="pdf(d1)/(S σ √T)",
    what="Acceleration of delta - why hedges fail near expiry ('gamma pin').",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["d1_d2", "delta"],
    interpretation="Highest ATM near expiry → dealer hedging pins index to max-OI strike."))

_add(FormulaDoc(
    id="theta", title="Theta (Time Decay)", category="options",
    latex=r"\Theta=\partial V/\partial t\ \ (\text{reported per day})",
    text_formula="analytic derivative of BS price wrt calendar time",
    what="Daily rental cost of long options - the enemy of week-long holds.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["delta"],
    interpretation="Never hold long OTM weeklies through the last 48h unless expecting a move."))

_add(FormulaDoc(
    id="vega", title="Vega (∂V/∂σ)", category="options",
    latex=r"\mathcal{V}=Se^{-qT}\phi(d_1)\sqrt{T}\ \ (\text{/100 per vol pt})",
    text_formula="S*pdf(d1)*sqrt(T), scaled per 1% IV",
    what="Event-driven pnl: budget/budget-day IV crush plays.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["delta"],
    interpretation="Sell premium when IV rank >80 pre-event (crush incoming); buy when IV rank <20 before catalysts."))

_add(FormulaDoc(
    id="rho", title="Rho (∂V/∂r)", category="options",
    latex=r"\rho_C=KTe^{-rT}N(d_2)",
    text_formula="discount-rate sensitivity; minor for weekly Indian options",
    what="Interest-rate sensitivity; matters for LEAPS-style positions.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["delta"]))

_add(FormulaDoc(
    id="implied_vol", title="Implied Volatility (bisection solver)", category="options",
    latex=r"\sigma_{iv}: BS(S,K,T,r;\sigma_{iv}) = \text{MarketPrice}",
    text_formula="root-find sigma where BS model price equals market premium",
    what="Market's own volatility forecast embedded in each strike - builds the smile you trade.",
    how=["Bracket σ∈[0.0001, 5.0]",
         "Check sign change of f(σ)=BS(σ)−market",
         "Brent's method converges to root"],
    inputs={"market price": "traded option premium"},
    depends_on=["bs_price", "newton_iv"],
    interpretation="IV percentile >70 → rich premium (sell strategies); <30 → cheap (buy). Smile skew direction reveals crash fear (puts richer)."))

_add(FormulaDoc(
    id="newton_iv", title="Newton-Raphson IV", category="options",
    latex=r"\sigma_{k+1}=\sigma_k-\frac{BS(\sigma_k)-P_{mkt}}{\partial BS/\partial \sigma}",
    text_formula="iterate sigma -= (model-market)/vega; fallback bisection",
    what="Fast IV solver using vega as slope; robust fallback keeps illiquid strikes solvable.",
    how=["Start guess σ₀=0.2", "Update via vega denominator",
         "If diverges/out of bounds → bisection"],
    depends_on=["implied_vol", "vega"]))

_add(FormulaDoc(
    id="put_call_parity", title="Put-Call Parity Arbitrage", category="options",
    latex=r"C-P=S-Ke^{-rT}\ \Rightarrow\ \text{gap}=(C-P)-(S-Ke^{-rT})",
    text_formula="C-P must equal S - K*e^(-rT); nonzero gap = synthetic arb",
    what="No-arbitrage identity exposing mispriced synthetics in Indian options.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["bs_price"],
    interpretation="Gap beyond costs+slippage → convert/reverse-conversion arb (usually captured by pros in ms)."))

_add(FormulaDoc(
    id="crr_american", title="CRR Binomial Tree (American)", category="options",
    latex=[r"u=e^{\sigma\sqrt{\Delta t}},\ d=1/u,\ p=\frac{e^{r\Delta t}-d}{u-d}",
           r"V_t=e^{-r\Delta t}[pVu+(1-p)Vd],\ \ V=\max(V,\ \text{intrinsic})"],
    text_formula="backward induction with early-exercise check each node",
    what="Prices American-style rights (early exercise) that BS-Europe cannot.",
    how=["Build recombining tree with u,d,p", "Terminal payoffs",
         "Discount backward one step at a time",
         "At every node take max(discounted continuation, intrinsic)"],
    depends_on=["bs_price"],
    interpretation="Early-exercise premium >0 mostly for deep ITM puts; guides whether holding vs exercising matters."))

_add(FormulaDoc(
    id="payoff_diagram", title="Strategy Payoff at Expiry", category="options",
    latex=r"\Pi(S_T)=\sum_i q_i\,[\text{intrinsic}_i(S_T)-\text{premium}_i]",
    text_formula="sum over legs of qty*(intrinsic - premium) evaluated across spot grid",
    what="The picture before every multi-leg trade: max profit, max loss, breakevens.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["bs_price"]))

_add(FormulaDoc(
    id="pcr", title="Put-Call Ratio (PCR)", category="options",
    latex=r"PCR=\frac{\sum PE\ OI}{\sum CE\ OI}",
    text_formula="total PE open interest / total CE open interest (per expiry)",
    what="Positioning thermometer for Indian index options.",
    how=["Sum PE OI across strikes", "Divide by summed CE OI"],
    interpretation="PCR>1.2 = put writers dominant (bullish floor); <0.7 = call writing pressure. Extremes often precede squeezes."))

_add(FormulaDoc(
    id="max_pain", title="Max Pain Strike", category="options",
    latex=r"K^*=\arg\min_K \sum_i \big[OI_{CE,i}\max(K-K_i,0)+OI_{PE,i}\max(K_i-K,0)\big]",
    text_formula="strike minimizing total payout to option holders across all OI",
    what="Where option writers profit most - magnet level into expiry week.",
    how=["For each candidate strike K", "Sum CE writer losses (K - strike)×CE_OI where ITM",
         "Add PE writer losses symmetrically", "Pick K minimizing total"],
    depends_on=["pcr"],
    interpretation="Spot drifts toward max pain in the final 3-4 sessions ~65% of weeks on Nifty."))

# ===================================================================== #
# MODELS
# ===================================================================== #
_add(FormulaDoc(
    id="gbm", title="Geometric Brownian Motion", category="model",
    latex=[r"dS_t=\mu S_t\,dt+\sigma S_t\,dW_t",
           r"S_T=S_0\exp\!\big[(\mu-\tfrac{\sigma^2}{2})T+\sigma W_T\big]"],
    text_formula="exact solution used for path simulation: log-increments are Normal(mu-0.5s^2, s^2 dt)",
    what="Baseline random-walk market model powering Monte Carlo scenarios everywhere.",
    how=["Estimate μ, σ from historical log returns",
         "Simulate Z~N(0,1) increments", "Accumulate exact log-solution"],
    inputs={"μ": "drift (annualized)", "σ": "volatility", "W_t": "Brownian motion"},
    depends_on=["estimate_gbm_params", "monte_carlo_gbm"],
    interpretation="Fat tails ignored - pair with jump diffusion for stress realism."))

_add(FormulaDoc(
    id="estimate_gbm_params", title="GBM Parameter Estimation (MoM)", category="model",
    latex=[r"\hat{\mu}_{ann}=\bar{r}_{daily}\times 252", r"\hat{\sigma}_{ann}=s_{daily}\sqrt{252}"],
    text_formula="mean & std of daily log returns annualized",
    what="Calibrates simulation inputs from OSINT price history.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["gbm"],
    interpretation="Sanity-check σ̂ vs implied vols; large gap = market pricing event risk."))

_add(FormulaDoc(
    id="monte_carlo_gbm", title="Monte Carlo Option Pricing", category="model",
    latex=[r"\hat{C}=e^{-rT}\frac{1}{M}\sum_m \max(S_T^{(m)}-K,0)",
           r"SE=e^{-rT}\frac{s_{payoff}}{\sqrt{M}}"],
    text_formula="average discounted payoffs across simulated terminals; SE = std/sqrt(M)",
    what="Prices any path-dependent claim & gives confidence intervals.",
    how=["Simulate M GBM terminal prices under Q (drift=r)",
         "Payoff per path", "Discount-mean = price",
         "Antithetic variates halve variance: pair Z with −Z"],
    depends_on=["gbm"],
    static_example={"M": 100000, "K": 24500, "S0": 24500, "σ": "12%", "T": "7d",
                    "note": "MC price should match BS within ~2*SE"}))

_add(FormulaDoc(
    id="merton_jd", title="Merton Jump Diffusion", category="model",
    latex=[r"dS=\mu S dt+\sigma S dW+S\,dJ_t",
           r"k=e^{m+v^2/2}-1,\ \ \mu_Q=r-\lambda k",
           r"J_t:\ \text{Poisson}(\lambda dt)\ \text{jumps sized } \ln J\sim N(m,v)"],
    text_formula="GBM plus Poisson-compensated jumps; compensator k keeps martingale property",
    what="Adds election/budget/war style gaps the normal model misses - realistic VaR tails.",
    how=["Draw Poisson jumps per step (λ≈3-5 events/yr for indices)",
         "Log-normal jump sizes", "Add to GBM increment, adjust drift by λk"],
    depends_on=["gbm"],
    interpretation="Calibrate λ,m,v from historical >3σ days; compare tail VaR vs plain GBM."))

_add(FormulaDoc(
    id="heston_model", title="Heston Stochastic Volatility", category="model",
    latex=[r"dS=\mu Sdt+\sqrt{v}S\,dW^S",
           r"dv=\kappa(\theta-v)dt+\xi\sqrt{v}\,dW^v,\ \ dW^S dW^v=\rho\,dt"],
    text_formula="variance follows its own mean-reverting square-root process correlated with spot",
    what="Generates realistic smiles/skew & vol clustering for scenario pricing.",
    how=["Simulate variance first (full-truncation Euler): keep v≥0",
         "Correlate shocks with ρ (negative = skew)",
         "Feed sqrt(v) into spot diffusion"],
    inputs={"κ": "variance mean-reversion speed", "θ": "long-run variance",
            "ξ": "vol-of-vol", "ρ": "spot-var correlation (India: −0.6…−0.8)"},
    depends_on=["gbm", "ewma_vol"],
    interpretation="θ tracks VIX regime; κ slow → vol persists → favor straddle holds over quick scalps."))

_add(FormulaDoc(
    id="ou_process", title="Ornstein-Uhlenbeck (Pairs Spread)", category="model",
    latex=[r"dx_t=\theta(\mu-x_t)dt+\sigma dW_t",
           r"\text{half-life}=\frac{\ln 2}{\theta}"],
    text_formula="mean-reverting AR(1) continuous limit; half-life from reversion speed",
    what="Models spread between paired stocks (HDFC vs ICICI etc.) - times reversion entries.",
    how=["OLS: dx = a + b·x → θ = −b/dt, μ = a/θdt",
         "σ from residual std", "Half-life = ln2/θ days"],
    depends_on=["ou_halflife"],
    interpretation="Trade when |z-score of spread|>2 with θ significant; skip pairs with half-life >15 days."))

_add(FormulaDoc(
    id="ou_halflife", title="OU Half-Life of Reversion", category="model",
    latex=r"t_{1/2}=\ln 2/\theta",
    text_formula="days for a dislocation to decay 50%",
    what="Sets the natural holding period & stop horizon for mean-reversion trades.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["ou_process"],
    static_example={"theta": "0.08/day", "half_life": "ln2/0.08 = 8.7 days"}))

# ===================================================================== #
# VOLATILITY
# ===================================================================== #
_add(FormulaDoc(
    id="realized_vol_cc", title="Realized Volatility (close-close)", category="volatility",
    latex=r"\sigma_{ann}=s\big(\ln(P_t/P_{t-1}),\,n\big)\times\sqrt{252}",
    text_formula="rolling stdev of daily log returns × sqrt(252)",
    what="Benchmark realized vol everything else is compared to.",
    how=["Daily log returns", "Rolling std over n", "Annualize ×√252"],
    depends_on=["ewma_vol", "parkinson"],
    static_example={"sd_daily": "1.2%", "annualized": "1.2%×15.87 = 19.05%"}))

_add(FormulaDoc(
    id="ewma_vol", title="EWMA Volatility (RiskMetrics)", category="volatility",
    latex=r"\sigma_t^2=\lambda\sigma_{t-1}^2+(1-\lambda)r_t^2,\quad \lambda=0.94",
    text_formula="recursive variance weighting recent shocks at 6%",
    what="Reacts fast to shocks - next-day vol forecast & MC input.",
    how=["Seed var = sample variance", "Update daily with λ=0.94 recursion",
         "√(252·var) annualize"],
    depends_on=["realized_vol_cc"],
    interpretation="Forecast jumps post-event days; compare vs ATM IV for edge direction."))

_add(FormulaDoc(
    id="parkinson", title="Parkinson Estimator", category="volatility",
    latex=r"\sigma_P=\sqrt{\frac{1}{4\ln 2}\,\overline{\ln^2(H/L)}}\times\sqrt{252}",
    text_formula="uses intraday high-low range; ~5x more efficient than CC",
    what="Range-based vol - captures information close-only series misses.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["garman_klass"]))

_add(FormulaDoc(
    id="garman_klass", title="Garman-Klass Estimator", category="volatility",
    latex=r"\sigma_{GK}^2=\overline{\tfrac12\ln^2\!\tfrac{H}{L}-(2\ln2-1)\ln^2\!\tfrac{C}{O}}",
    text_formula="OHLC efficient estimator, ~7.4x efficiency of CC",
    what="Best free lunch among classical estimators for daily OHLC data.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["yang_zhang"]))

_add(FormulaDoc(
    id="rogers_satchell", title="Rogers-Satchell Estimator", category="volatility",
    latex=r"\sigma_{RS}^2=\overline{(H-O)(H-C)+(L-O)(L-C)}",
    text_formula="drift-independent OHLC variance estimator",
    what="Handles trending markets without drift bias (unlike GK/Parkinson).",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["yang_zhang"]))

_add(FormulaDoc(
    id="yang_zhang", title="Yang-Zhang Estimator", category="volatility",
    latex=r"\sigma_{YZ}^2=\sigma_{overnight}^2+k\,\sigma_{open\to close}^2+(1-k)\sigma_{RS}^2",
    text_formula="blends overnight gap variance with intraday RS variance, optimal k",
    what="Gold-standard OHLC estimator: handles gaps AND drift - use for Indian markets with frequent gaps.",
    how=["Overnight variance: open vs prev close", "OS variance + RS component",
         "Optimal k = 0.34/(1.34+(n+1)/(n−1))"],
    depends_on=["rogers_satchell", "parkinson"],
    interpretation="When YZ >> IV: options cheap relative to realized behavior (buy premium)."))

_add(FormulaDoc(
    id="vol_cone", title="Volatility Cone", category="volatility",
    latex=r"\text{cone}(n):\ \{P_{10},P_{25},P_{50},P_{75},P_{90}\}\ \text{of }\sigma_n",
    text_formula="distribution percentiles of realized vol per horizon vs current",
    what="Answers: is TODAY'S vol expensive or cheap historically?",
    how=["Compute realized vol for windows 5/10/21/42/63d",
         "Percentiles across history", "Plot current point against cone"],
    depends_on=["realized_vol_cc"],
    interpretation="Current above p75 → vol-rich (sell premium); below p25 → vol-poor (buy)." ))

_add(FormulaDoc(
    id="atr_percentile", title="ATR Percentile Regime", category="volatility",
    latex=r"\%\,rank=\frac{\#\{ATR_{hist}<ATR_{today}\}}{N}\times100",
    text_formula="where today's ATR sits in past year's distribution (0-100)",
    what="Regime dial: quiet vs explosive tape for sizing decisions.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["atr"],
    interpretation="<30 quiet (size up), 30-70 normal, >70 explosive (halve size, widen stops)."))

# ===================================================================== #
# BACKTEST METRICS
# ===================================================================== #
_add(FormulaDoc(
    id="cagr", title="CAGR (Compound Annual Growth Rate)", category="metrics",
    latex=r"CAGR=\Big(\frac{V_{end}}{V_{start}}\Big)^{1/Y}-1",
    text_formula="geometric annualized growth over Y years",
    what="Comparable annual return across strategies/periods.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["total_return"],
    static_example={"start": 500000, "end": 800000, "years": 2,
                    "cagr": "(8/5)^0.5 - 1 = 26.5%"}))

_add(FormulaDoc(
    id="total_return", title="Total Return", category="metrics",
    latex=r"R=\frac{V_{end}-V_{start}}{V_{start}}",
    text_formula="simple period return",
    what="Raw P&L percentage before annualization.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["cagr"]))

_add(FormulaDoc(
    id="sharpe_ratio", title="Sharpe Ratio", category="metrics",
    latex=r"S=\frac{\bar{R}_p-R_f}{\sigma_p},\quad\text{annualized}\times\sqrt{252}",
    text_formula="(mean excess daily return / std of returns) * sqrt(252)",
    what="Return per unit of total risk - primary strategy quality score.",
    how=["Daily strategy returns", "Subtract rf/252 from mean",
         "Divide by daily std", "Annualize ×√252"],
    inputs={"R_f": "risk-free (~6.5% India)"},
    interpretation="<0.5 weak, 0.5-1 decent, 1-2 very good, >2 suspicious (check lookahead/fees!)."))

_add(FormulaDoc(
    id="sortino_ratio", title="Sortino Ratio", category="metrics",
    latex=r"So=\frac{\bar{R}_p-R_f}{\sigma_{downside}},\quad \sigma_D=\sqrt{\overline{\min(r,0)^2}}",
    text_formula="like Sharpe but only penalizes downside deviation",
    what="Fairer for asymmetric strategies (trend following has many small wins).",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["sharpe_ratio"],
    interpretation="Sortino >> Sharpe indicates upside-skewed return profile."))

_add(FormulaDoc(
    id="max_drawdown", title="Maximum Drawdown", category="metrics",
    latex=r"MDD=\min_t\Big(\frac{V_t-\max_{s\le t}V_s}{\max_{s\le t}V_s}\Big)",
    text_formula="worst peak-to-trough equity decline",
    what="The number that decides if you can actually survive holding the strategy.",
    how=["Running peak of equity curve", "DD_t = equity/peak - 1",
         "Report minimum (most negative)"],
    depends_on=["calmar_ratio"],
    interpretation="Personal rule: if MDD>25% cut position sizing until equity recovers."))

_add(FormulaDoc(
    id="calmar_ratio", title="Calmar Ratio", category="metrics",
    latex=r"C=\frac{CAGR}{|MDD|}",
    text_formula="annualized return / max drawdown",
    what="Return per unit of worst-case pain.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["cagr", "max_drawdown"],
    interpretation=">1 good, >3 excellent (rare outside trend funds)."))

_add(FormulaDoc(
    id="win_rate", title="Win Rate & Payoff Matrix", category="metrics",
    latex=r"W=\frac{N_{wins}}{N_{trades}},\quad PF=\frac{\Sigma wins}{|\Sigma losses|},\quad E=W\cdot\bar{Win}-(1-W)\cdot\bar{Loss}",
    text_formula="win rate, profit factor, expectancy per trade",
    what="The trio that defines edge quality; expectancy is what compounds.",
    how=["Count winning trades / total", "Sum profits / sum abs losses = PF",
         "Expectancy = avg $ made per trade including losers"],
    interpretation="60% win rate with RR 1:2 beats 40% with RR 1:1 only if PF>1.3. Always optimize EXPECTANCY not win rate alone.",
    static_example={"trades": 100, "wins": 55, "avg_win": 8000, "avg_loss": 4500,
                    "expectancy": "0.55*8000 - 0.45*4500 = ₹2375/trade",
                    "PF": "440000/202500 = 2.17"}))

_add(FormulaDoc(
    id="profit_factor", title="Profit Factor", category="metrics",
    latex=r"PF=\frac{\sum \text{gross profit}}{|\sum \text{gross loss}|}",
    text_formula="rupees won / rupees lost",
    what="Robustness gauge independent of trade count.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["win_rate"],
    interpretation="<1 losing; 1.3+ deployable; >2 excellent; >4 verify no survivorship bias."))

_add(FormulaDoc(
    id="exposure_time", title="Exposure Time", category="metrics",
    latex=r"E=\frac{\text{bars in market}}{\text{total bars}}\times100\%",
    text_formula="share of sessions with open risk",
    what="Capital efficiency + overnight-gap risk measure.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    interpretation="Low exposure + high CAGR = best risk-adjusted compounding machines."))

# ===================================================================== #
# RISK
# ===================================================================== #
_add(FormulaDoc(
    id="kelly_criterion", title="Kelly Criterion Position Size", category="risk",
    latex=[r"f^*=W-\frac{1-W}{RR}", r"\text{size}=\frac{f^*\cdot\text{Capital}}{\text{entry}}"],
    text_formula="fraction of capital = W - (1-W)/RR; use HALF-Kelly in practice",
    what="Mathematically optimal growth fraction given your win rate & payoff.",
    how=["Estimate W (win prob) & RR from backtest",
         "Apply Kelly formula", "HALVE it - full Kelly volatility is brutal"],
    inputs={"W": "win rate", "RR": "avg win/avg loss"},
    depends_on=["win_rate"],
    static_example={"W": 0.55, "RR": 1.8, "f*": "0.55 - 0.45/1.8 = 0.30",
                    "half-kelly": "15% of capital max per idea"}))

_add(FormulaDoc(
    id="atr_position_size", title="ATR-Based Position Sizing", category="risk",
    latex=r"N=\frac{f\cdot Capital}{2\cdot ATR},\quad f=RiskPerTrade\%",
    text_formula="shares = (risk% * capital) / (stop_distance = 2*ATR)",
    what="Equalizes rupee-risk across every trade regardless of stock volatility.",
    how=["Rupee risk = 1% × capital", "Stop distance = 2×ATR",
         "Shares = risk/stop_distance", "Cap by margin available"],
    depends_on=["atr", "fixed_fractional"],
    static_example={"capital": 500000, "risk%": 1, "risk_rs": 5000,
                    "ATR": 25, "stop_dist": 50, "qty": 100,
                    "check": "100 shares × 50 stop = ₹5000 ✓"}))

_add(FormulaDoc(
    id="fixed_fractional", title="Fixed Fractional Risk", category="risk",
    latex=r"Risk_\₹=Capital\times r\%,\quad Qty=\lfloor Risk_\₹/|Entry-Stop|\rfloor",
    text_formula="risk fixed % of CURRENT equity per trade (compounding-safe)",
    what="Prevents ruin during drawdowns - risk shrinks as equity shrinks.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["atr_position_size", "kelly_criterion"],
    interpretation="1% per trade × max 10 concurrent = max 10% heat. Never exceed 3% single-trade risk."))

_add(FormulaDoc(
    id="var_historical", title="Value at Risk (VaR)", category="risk",
    latex=[r"\text{VaR}_\alpha=F_R^{-1}(1-\alpha)\times V",
           r"\text{MC: } VaR=-q_{(1-\alpha)}\big(\{r^{sim}\}\big)V"],
    text_formula="loss threshold not exceeded with alpha% confidence over horizon",
    what="One-number downside estimate regulators/exchanges think in.",
    how=["Historical or simulated return distribution",
         "Take (1−α) quantile (e.g. 5%)", "Scale by portfolio value"],
    inputs={"α": "confidence (95/99)", "horizon": "days"},
    depends_on=["cvar", "monte_carlo_gbm"],
    static_example={"portfolio": "₹10,00,000", "alpha": 95, "horizon": "1d",
                    "VaR": "-1.8% → ₹18,000 worst typical day"}))

_add(FormulaDoc(
    id="cvar", title="Conditional VaR (Expected Shortfall)", category="risk",
    latex=r"CVaR=E[r\mid r\le VaR]",
    text_formula="average loss GIVEN that VaR was breached",
    what="Answers 'how bad is bad?' - coherent risk measure VaR ignores.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["var_historical"],
    interpretation="CVaR/VaR ratio >1.5 = fat-tailed portfolio → trim leverage."))

_add(FormulaDoc(
    id="rr_ratio", title="Reward:Risk & R-Multiples", category="risk",
    latex=[r"RR=\frac{|T-entry|}{|entry-stop|}", r"R=\frac{\text{trade P&L}}{\text{initial risk}}"],
    text_formula="target distance over stop distance; results measured in R units",
    what="Universal language to grade every trade identically across stocks.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["atr_position_size"],
    interpretation="Minimum acceptable RR 1.5 for swing entries; scale-out at +1R keeps expectancy positive even at 40% accuracy."))

_add(FormulaDoc(
    id="heat_management", title="Portfolio Heat", category="risk",
    latex=r"H=\sum_i \frac{Risk_i}{Capital}\times100\%",
    text_formula="sum of open-trade risks as % of equity",
    what="Aggregate exposure guardrail during correlated market drops.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    interpretation="Max heat 6-10%; pause new entries when breached; correlated sector counts double."))

# ===================================================================== #
# PORTFOLIO
# ===================================================================== #
_add(FormulaDoc(
    id="markowitz_variance", title="Markowitz Mean-Variance", category="portfolio",
    latex=[r"\min_w\ w^\top\Sigma w\ \ \text{s.t.}\ \ w^\top\mu=\mu^*,\ \mathbf{1}^\top w=1",
           r"w\ge 0\ \text{(long-only)}"],
    text_formula="quadratic program minimizing covariance-weighted variance for target return",
    what="Foundational diversification math - finds the efficient frontier.",
    how=["Estimate μ, Σ from returns", "Solve QP via SLSQP for each target return",
         "Trace frontier; pick tangency (max Sharpe)"],
    inputs={"Σ": "annualized covariance matrix", "μ": "expected returns"},
    depends_on=["max_sharpe_objective", "efficient_frontier"],
    interpretation="Estimation error is real - shrink μ toward grand mean or prefer HRW below."))

_add(FormulaDoc(
    id="max_sharpe_objective", title="Max Sharpe (Tangency) Portfolio", category="portfolio",
    latex=r"\max_w\ \frac{w^\top\mu-r_f}{\sqrt{w^\top\Sigma w}}",
    text_formula="optimize weights for highest excess-return-per-volatility",
    what="Single 'best' allocation on the frontier for a given rf.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["markowitz_variance", "sharpe_ratio"]))

_add(FormulaDoc(
    id="efficient_frontier", title="Efficient Frontier Generation", category="portfolio",
    latex=r"\{( \sigma(w^*(\mu^*)), \mu^* ):\ \mu^*\in[\mu_{min},\mu_{max}]\}",
    text_formula="solve min-variance QP across grid of target returns",
    what="Visual menu of achievable risk-return combos for capital allocation decisions.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["markowitz_variance"]))

_add(FormulaDoc(
    id="hrp_cluster_var", title="Hierarchical Risk Parity (HRP)", category="portfolio",
    latex=[r"D=\sqrt{\frac{1-Corr}{2}},\ \ \text{cluster via linkage}",
           r"w_c \propto \frac{1}{Var(c)},\ \ \text{recursive bisecting split}"],
    text_formula="weights inverse cluster-variance down a dendrogram - no μ estimation needed",
    what="Machine-learning diversification robust to garbage return estimates - our default allocator.",
    how=["Correlation → distance matrix", "Hierarchical clustering (single linkage)",
         "Recursive bisection allocating weight inversely to cluster variance"],
    depends_on=["markowitz_variance"],
    interpretation="HRP portfolios show shallower drawdowns in Indian sector rotations vs naive Markowitz."))

# ===================================================================== #
# MARKET INTELLIGENCE
# ===================================================================== #
_add(FormulaDoc(
    id="fii_dii_regime_score", title="FII/DII Regime Bias Score", category="market",
    latex=[r"S_{FII}=\frac{\sum_{d=1}^{5} w_d\cdot Net_d}{\sum w_d},\ w_d=d",
           r"\text{bias}=\mathrm{clip}\big(S_{FII}/5000,-1,+1\big)"],
    text_formula="recency-weighted average of FII net flows (cr) normalized by ±5000cr extreme-session scale → -1..+1",
    what="Converts raw institutional flow prints into a tradable regime dial.",
    how=["Pull daily FII cash net figures", "Weight recent days linearly (today=5 … day-5=1)",
         "Normalize: +5000cr day = +1 (extreme bull flow)"],
    interpretation=">+0.25 ride longs aggressively; <−0.25 tighten stops/shrink size; DIIs buying while FIIs sell = dip-protection regime.",
    static_example={"nets(cr)": "[-3200,-1800,+900,-2400,-3600]", "weighted_avg": "-2417",
                    "bias": "-0.48 → BEARISH regime"}))

_add(FormulaDoc(
    id="whale_score", title="Whale Accumulation Score (0-100)", category="market",
    latex=[r"S=8\cdot\mathrm{clip}(z_V,0,6)+15\cdot\min(D_{spike},2)+22\cdot\frac{\mathrm{clip}(Net_{inst},-200,200)}{200}",
           r"D_{spike}=\frac{\text{Delivery}\%_{today}}{\overline{\text{Delivery}\%}}"],
    text_formula="volume anomaly (≤48pts) + delivery spike (≤30pts) + net institutional deal value (≤22pts)",
    what="Composite radar for hidden institutional accumulation before price moves.",
    how=["Volume z-score contribution (capped)", "Delivery% spike vs baseline",
         "Bulk/block deal net institutional value normalized ±200cr",
         "Sum & clip to 100"],
    inputs={"z_V": "today's volume z-score", "Net_inst": "inst buy − inst sell (cr)"},
    depends_on=["volume_zscore", "delivery_spike", "volume_anomaly"],
    interpretation="≥65 STRONG ACCUMULATION (investigate fundamentals/news), 45-64 watchlist, ≤20 DISTRIBUTION avoid longs."))

_add(FormulaDoc(
    id="delivery_spike", title="Delivery % Spike", category="market",
    latex=r"D_{spike}=\frac{Deliv\%_t}{\overline{Deliv\%}_{baseline}}",
    text_formula="today's delivery ratio ÷ its recent baseline",
    what="Separates real investor accumulation from intraday speculation churn.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["whale_score"],
    interpretation="Delivery >2× baseline on up-move = institutions taking delivery (bullish); high price gain + LOW delivery = operator pump."))

_add(FormulaDoc(
    id="volume_anomaly", title="Volume Anomaly Detection", category="market",
    latex=r"z_V=\frac{V_t-\mu_{20}(V)}{\sigma_{20}(V)}",
    text_formula="same as volume z-score; feeds whale score",
    what="First-responder signal that something changed BEFORE news breaks publicly.",
    how=["See formula definition - apply inputs as documented",
           "Compute stepwise per the LaTeX above"],
    depends_on=["volume_zscore"]))

_add(FormulaDoc(
    id="screener_composite", title="Screener Composite Score", category="market",
    latex=r"Score=0.35\,Trend+0.25\,Mom+0.20\,Strength+0.20\,\min(Prox,100)",
    text_formula="weighted blend of four 0-100 factor scores",
    what="Single ranking number to triage 90+ symbols into tonight's watchlist.",
    how=["Trend: graded distance above EMA200 (40pts) & EMA50 (30pts) + Supertrend green (30)",
         "Momentum: gaussian preference peaking at RSI 58; penalized <45/>80",
         "Strength: logistic curve on ADX (0-55) + volume z-score bonus (0-45)",
         "Proximity: closeness to 52w high (0-100)"],
    depends_on=["adx", "rsi", "supertrend", "relative_strength"],
    interpretation="Top-decile scores + FII bias>0 = A+ candidates; cross-check whale score before pulling trigger."))

# ===================================================================== #
# FUTURES & OPTIONS ANALYTICS
# ===================================================================== #

_add(FormulaDoc(
    id="cost_of_carry", title="Cost of Carry (Futures)", category="model",
    latex=r"F = S \cdot e^{(r-q)T} \implies r-q = \frac{\ln(F/S)}{T}",
    text_formula="implied carry = ln(F/S) / T where T = DTE/365",
    what="Implied financing cost minus dividend yield embedded in futures price.",
    how=["Compute ln(Futures/Spot)", "Divide by time to expiry in years"],
    inputs={"F": "futures price", "S": "spot price", "T": "time to expiry (years)"},
    interpretation="Carry > risk-free rate = rich futures (contango). Carry < rf = backwardation.",
    static_example={"spot": 24500, "futures": 24580, "dte": 30, "implied_carry": "0.065 (6.5%)"}))

_add(FormulaDoc(
    id="futures_fair_value", title="Futures Fair Value", category="model",
    latex=r"F_{fair} = S \cdot e^{(r-q)T}",
    text_formula="fair = spot * exp((risk_free - div_yield) * T)",
    what="Theoretical futures price under no-arbitrage cost-of-carry.",
    how=["Spot * exp((r - q) * T)"], inputs={"S": "spot", "r": "risk-free", "q": "div yield", "T": "years"},
    interpretation="Futures > fair = overpriced (sell futures, buy spot). Futures < fair = underpriced."))

_add(FormulaDoc(
    id="futures_basis", title="Futures Basis & Annualized Basis", category="model",
    latex=[r"Basis = F - S", r"Basis\% = \frac{F-S}{S} \times 100",
           r"Annualized = Basis\% \times \frac{365}{DTE}"],
    text_formula="basis = F - S; basis% = (F-S)/S*100; annualized = basis% * 365/DTE",
    what="Difference between futures and spot; annualized for comparability.",
    how=["Basis = Futures - Spot", "Annualize by 365/DTE"],
    interpretation="Positive annualized basis = contango. Negative = backwardation. Large basis = rich futures."))

_add(FormulaDoc(
    id="cash_futures_arbitrage", title="Cash-Futures Arbitrage Bounds", category="model",
    latex=[r"F_{lower} = S \cdot e^{(r-q)T} - TC", r"F_{upper} = S \cdot e^{(r-q)T} + TC",
           r"Mispricing = F_{market} - F_{fair}"],
    text_formula="fair = S*exp((r-q)T); bounds = fair ± transaction_cost; signal = market - fair",
    what="No-arbitrage bounds for futures price; signals mispricing beyond transaction costs.",
    how=["Compute fair value", "Apply transaction cost bands", "Compare market price"],
    interpretation="Market > upper = sell futures + buy spot. Market < lower = buy futures + sell spot."))

_add(FormulaDoc(
    id="futures_greeks", title="Futures Greeks", category="model",
    latex=[r"\Delta = 1", r"\Gamma = 0", r"\Theta = -(r-q) \cdot F / 365",
           r"\mathcal{V} = 0", r"\rho = F \cdot T"],
    text_formula="Delta=1, Gamma=0, Theta=-carry*F/365, Vega=0, Rho=F*T",
    what="Linear sensitivity of futures to underlying, rates, time.",
    how=["Delta=1 (linear)", "Theta = -annual_carry*F/365 per day", "Rho = F*T"],
    interpretation="Futures have no gamma/vega; theta = daily cost of carry decay."))

_add(FormulaDoc(
    id="roll_yield", title="Calendar Spread Roll Yield", category="model",
    latex=r"Roll = \frac{F_{far} - F_{near}}{F_{near}} \times \frac{365}{DTE_{far} - DTE_{near}}",
    text_formula="roll% = (far - near)/near * 365/(DTE_far - DTE_near)",
    what="Annualized yield from rolling near-month futures to far-month.",
    how=["Spread = far - near", "Annualize by 365/day_diff"],
    interpretation="Positive roll yield = backwardation (profitable to roll long). Negative = contango (cost to roll)."))

_add(FormulaDoc(
    id="capm_alpha_beta", title="CAPM Alpha & Beta", category="metrics",
    latex=[r"r_a - r_f = \alpha + \beta (r_m - r_f) + \epsilon",
           r"\beta = \frac{Cov(r_a, r_m)}{Var(r_m)}", r"\alpha = \bar{r}_a - r_f - \beta(\bar{r}_m - r_f)"],
    text_formula="excess return = alpha + beta * market_excess_return",
    what="Risk-adjusted performance vs benchmark; alpha = skill, beta = market sensitivity.",
    how=["Regress excess returns on market excess", "Alpha = intercept, Beta = slope"],
    inputs={"returns": "asset daily returns", "benchmark": "market daily returns", "rf": "risk-free"},
    interpretation="Alpha > 0 = outperformance. Beta > 1 = aggressive. Beta < 1 = defensive.",
    static_example={"alpha_annual": "3.2%", "beta": "1.15", "r2": "0.78", "info_ratio": "0.85"}))

_add(FormulaDoc(
    id="capm_alpha_beta", title="CAPM Alpha & Beta", category="metrics",
    latex=[r"r_a - r_f = \alpha + \beta (r_m - r_f) + \epsilon",
           r"\beta = \frac{Cov(r_a, r_m)}{Var(r_m)}", r"\alpha = \bar{r}_a - r_f - \beta(\bar{r}_m - r_f)"],
    text_formula="excess return = alpha + beta * market_excess_return",
    what="Risk-adjusted performance vs benchmark; alpha = skill, beta = market sensitivity.",
    how=["Regress excess returns on market excess", "Alpha = intercept, Beta = slope"],
    inputs={"returns": "asset daily returns", "benchmark": "market daily returns", "rf": "risk-free"},
    interpretation="Alpha > 0 = outperformance. Beta > 1 = aggressive. Beta < 1 = defensive.",
    static_example={"alpha_annual": "3.2%", "beta": "1.15", "r2": "0.78", "info_ratio": "0.85"}))

_add(FormulaDoc(
    id="full_greeks", title="Complete Options Greeks (incl. 2nd/3rd order)", category="options",
    latex=[r"\text{Vanna} = \frac{\partial \Delta}{\partial \sigma} = -\frac{d_2 \Gamma}{\sigma}",
           r"\text{Volga} = \frac{\partial \mathcal{V}}{\partial \sigma} = \mathcal{V} \frac{d_1 d_2}{\sigma}",
           r"\text{Charm} = \frac{\partial \Delta}{\partial t}",
           r"\text{Speed} = \frac{\partial \Gamma}{\partial S}",
           r"\text{Color} = \frac{\partial \Gamma}{\partial t}",
           r"\text{Zomma} = \frac{\partial \Gamma}{\partial \sigma}"],
    text_formula="2nd/3rd order: Vanna, Volga, Charm, Speed, Color, Zomma",
    what="Higher-order Greeks for advanced risk management (vol exposure, time decay of delta, etc.).",
    how=["Compute base Greeks", "Apply analytical formulas for each higher-order"],
    inputs={"S": "spot", "K": "strike", "T": "time", "r": "rate", "σ": "vol", "type": "CE/PE"},
    interpretation="Vanna = delta's vol sensitivity. Volga = vega's vol sensitivity. Charm = delta decay."))

_add(FormulaDoc(
    id="skew_metrics", title="IV Skew: 25d Risk Reversal & Butterfly", category="options",
    latex=[r"RR_{25d} = IV_{25d\,Call} - IV_{25d\,Put}",
           r"BF_{25d} = \frac{IV_{25d\,Call} + IV_{25d\,Put}}{2} - IV_{ATM}"],
    text_formula="RR = 25d Call IV - 25d Put IV; BF = avg(25d Call, 25d Put) - ATM IV",
    what="Measure of skew (put vs call demand) and smile curvature.",
    how=["Find 25 delta strikes", "RR = Call25 - Put25", "BF = avg(25s) - ATM"],
    interpretation="RR > 0 = calls richer (bullish skew). RR < 0 = puts richer (bearish). BF > 0 = smile."))

_add(FormulaDoc(
    id="max_pain", title="Max Pain Strike", category="options",
    latex=r"K^* = \arg\min_K \sum [OI_{CE} \max(K-K_i,0) + OI_{PE} \max(K_i-K,0)]",
    text_formula="strike minimizing total writer loss across all OI",
    what="Strike where option writers lose least; magnet level near expiry.",
    how=["For each strike K, sum CE_loss = OI_CE * max(K-Ki,0) + PE_loss = OI_PE * max(Ki-K,0)", "Pick K minimizing total"],
    interpretation="Spot gravitates to max pain in expiry week. Distance > 2% = high conviction move away."))

_add(FormulaDoc(
    id="pcr_analysis", title="Put-Call Ratio (PCR) Analysis", category="options",
    latex=r"PCR_{OI} = \frac{\sum PE\_OI}{\sum CE\_OI}, \quad PCR_{Vol} = \frac{\sum PE\_Vol}{\sum CE\_Vol}",
    text_formula="PCR_OI = total_PE_OI / total_CE_OI; PCR_Vol = total_PE_Vol / total_CE_Vol",
    what="Positioning indicator from open interest and volume.",
    how=["Sum all PE OI", "Divide by total CE OI", "Same for volume"],
    interpretation="PCR > 1.2 = put writers dominant (bullish floor). PCR < 0.8 = call writers dominant."))

_add(FormulaDoc(
    id="max_pain", title="Max Pain Strike", category="options",
    latex=r"K^* = \arg\min_K \sum [OI_{CE} \max(K-K_i,0) + OI_{PE} \max(K_i-K,0)]",
    text_formula="strike minimizing total writer loss across all OI",
    what="Strike where option writers lose least; magnet level near expiry.",
    how=["For each strike K, sum CE_loss = OI_CE * max(K-Ki,0) + PE_loss = OI_PE * max(Ki-K,0)", "Pick K minimizing total"],
    interpretation="Spot gravitates to max pain in expiry week. Distance > 2% = high conviction move away."))

_add(FormulaDoc(
    id="put_call_parity_detailed", title="Put-Call Parity Deviation", category="options",
    latex=r"C - P = S - K e^{-rT} \implies \text{Gap} = (C-P) - (S - K e^{-rT})",
    text_formula="Gap = (Call - Put) - (Spot - Strike * exp(-rT))",
    what="No-arbitrage relationship between calls, puts, spot, and strike.",
    how=["Compute C - P from market", "Compute S - K*exp(-rT)", "Gap = difference"],
    interpretation="Gap > costs = arbitrage (sell call, buy put, buy spot, borrow). Gap < -costs = reverse arb."))

_add(FormulaDoc(
    id="oi_walls", title="OI Walls (Support/Resistance from OI)", category="market",
    latex=r"Resistance = strikes with max CE\_OI > spot; Support = strikes with max PE\_OI < spot",
    text_formula="Resistance = top CE OI strikes > spot; Support = top PE OI strikes < spot",
    what="High OI strikes act as magnetic support/resistance levels.",
    how=["Filter CE OI > spot, take top N", "Filter PE OI < spot, take top N"],
    interpretation="High CE OI = call writers defending resistance. High PE OI = put writers defending support."))

_add(FormulaDoc(
    id="delta_neutral_hedge", title="Delta-Neutral Hedge Ratio", category="risk",
    latex=r"Hedge\_Qty = -\sum (\Delta_i \times Qty_i)",
    text_formula="hedge futures qty = -sum(option_delta * qty)",
    what="Futures contracts needed to delta-hedge an options portfolio.",
    how=["Sum delta * qty across all positions", "Short that many futures"],
    interpretation="Neutralizes directional risk; leaves gamma/vega exposure. Rebalance as delta changes."))

_add(FormulaDoc(
    id="gamma_scalping", title="Gamma Scalping P&L", category="risk",
    latex=r"PnL_{gamma} = \frac{1}{2} \Gamma \sum (dS)^2 - \Theta \cdot t",
    text_formula="gamma PnL = 0.5 * gamma * sum(dS^2); net = gamma_pnl - theta_cost",
    what="P&L from dynamically delta-hedging a long gamma position.",
    how=["Track daily spot moves", "Gamma PnL = 0.5 * gamma * sum(dS^2)", "Subtract theta decay"],
    interpretation="Profitable if realized vol > implied vol. Requires frequent rebalancing."))

_add(FormulaDoc(
    id="implied_dividend_yield", title="Implied Dividend Yield from Futures", category="model",
    latex=r"q = r - \frac{\ln(F/S)}{T}",
    text_formula="implied_div_yield = risk_free - ln(F/S)/T",
    what="Market-implied dividend yield extracted from futures basis.",
    how=["Compute ln(Futures/Spot)", "Divide by T", "Subtract from risk-free rate"],
    interpretation="High implied yield = futures pricing in large dividends. Compare to actual declarations."))

_add(FormulaDoc(
    id="implied_forward_rate", title="Implied Forward Rate", category="model",
    latex=r"r_{fwd} = \frac{\ln(F/S)}{T}",
    text_formula="forward_rate = ln(F/S) / T",
    what="Risk-free rate implied by futures price.",
    how=["Compute ln(F/S)", "Divide by T (years)"],
    interpretation="Compare to actual risk-free rate. Higher = futures rich. Lower = futures cheap."))

_add(FormulaDoc(
    id="scenario_analysis", title="Scenario Analysis (What-if)", category="risk",
    latex=r"PnL = \sum Qty \times [BS(S_{new}, K, T_{new}, \sigma_{new}) - Premium]",
    text_formula="revalue all positions under shocked spot/vol/time",
    what="What-if P&L and Greeks under spot/vol/time shocks.",
    how=["Define spot/vol/time shocks", "Revalue all positions with BS", "Aggregate P&L and Greeks"],
    interpretation="Shows portfolio sensitivity to market moves. Use for stress testing and sizing."))

_add(FormulaDoc(
    id="span_margin_estimate", title="SPAN Margin Estimate (Simplified)", category="risk",
    latex=[r"Futures: SPAN = 12\% \times Notional; Exposure = 50\% \times Vol \times Notional",
           r"Short Options: SPAN = 15\% \times Notional; Exposure = 30\% \times Vol \times Notional",
           r"Long Options: SPAN = Premium Paid"],
    text_formula="Futures: 12% notional + 50%*vol*notional; Short opt: 15% notional + 30%*vol*notional; Long opt: premium",
    what="Rough SPAN-like margin estimate for portfolio margining.",
    how=["Classify position type", "Apply SPAN % to notional", "Add exposure margin for vol"],
    interpretation="Rough guide only. Actual SPAN uses complex risk arrays. Use for sizing estimates."))
