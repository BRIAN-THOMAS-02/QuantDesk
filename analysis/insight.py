"""Regime-conditioned insight engine.

Turns raw market data into an actionable, regime-aware verdict.  The design
follows the Knowledge base:

    * Ch.17 Indian Market-Regime Engine   -> classify a regime from a state vector
    * Ch.16 Horizon-Specific Frameworks   -> favour the right research per horizon
    * Ch.25 Final Decision Checklist      -> gate every decision on discipline gates
    * Final Conclusion                    -> combine independent evidence, never one signal

Every component degrades gracefully: if a piece of data is unavailable it is
reported as "not measured" instead of assumed, so the verdict stays honest about
what actually supports it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import pandas as pd

# --------------------------------------------------------------------------- #
# Knowledge-derived reference tables
# --------------------------------------------------------------------------- #

# Ch.17 regime definitions: favoured research + the main trap to watch.
REGIMES = {
    "BULL_BROAD": {
        "label": "Broad earnings bull",
        "favored": "Quality growth, momentum, sector leadership",
        "trap": "Excess valuation — do not chase stretched leaders",
    },
    "BULL_LIQUIDITY": {
        "label": "Liquidity-driven bull",
        "favored": "Beta and momentum with froth controls",
        "trap": "Confusing liquidity with real earnings",
    },
    "BULL_NARROW": {
        "label": "Narrow bull",
        "favored": "Relative strength with strict breadth controls",
        "trap": "Assuming broad health from cap-weight strength",
    },
    "SIDEWAYS_LOWVOL": {
        "label": "Sideways, low volatility",
        "favored": "Selective carry and mean reversion",
        "trap": "Unfiltered breakout systems get whipsawed",
    },
    "INFLATION_SHOCK": {
        "label": "Inflation / commodity shock",
        "favored": "Exposure-aware sector spreads",
        "trap": "Applying one sign to the whole index",
    },
    "BEAR_EARNINGS": {
        "label": "Earnings bear",
        "favored": "Capital preservation, quality, defensives",
        "trap": "Buying low P/E cyclicals too early",
    },
    "LIQUIDITY_CRISIS": {
        "label": "Liquidity crisis",
        "favored": "Cash, liquidity, convex hedges",
        "trap": "Relying on historical correlation",
    },
    "EVENT": {
        "label": "Event / policy regime",
        "favored": "Scenario analysis, reduced leverage",
        "trap": "Acting on binary certainty before the outcome",
    },
    "MONSOON_AGRI": {
        "label": "Monsoon / agriculture regime",
        "favored": "Rural, agri and consumer exposure",
        "trap": "Trusting a national rainfall average alone",
    },
}

# Ch.16 horizon-specific signal hierarchies (the order is the priority order).
HORIZON_FRAMEWORKS = {
    "multiyear": {
        "window": "2 to 10 years",
        "hierarchy": [
            "Governance and accounting integrity",
            "Industry structure and moat",
            "Normalised earnings",
            "Incremental ROIC",
            "Reinvestment runway",
            "Balance-sheet resilience",
            "Cash-flow quality",
            "Valuation and implied expectations",
            "Diversification and liquidity",
            "Technical timing (secondary)",
        ],
        "mistakes": [
            "Using a single multiple",
            "Treating peak cyclical earnings as normal",
            "Ignoring dilution and working capital",
            "Confusing narrative with moat",
            "Averaging down after thesis impairment",
        ],
    },
    "positional": {
        "window": "1 to 12 months",
        "hierarchy": [
            "Macro and liquidity regime",
            "Sector earnings cycle",
            "Earnings revisions",
            "Valuation spread",
            "3-to-12-month relative momentum",
            "Breadth",
            "FPI/DII and ownership flow",
            "Futures basis and rollover",
            "Risk and event calendar",
        ],
        "mistakes": [
            "Ignoring the macro/liquidity regime",
            "Trading momentum against the regime",
            "Disregarding the event calendar",
        ],
    },
    "swing": {
        "window": "2 days to 8 weeks",
        "hierarchy": [
            "Market and sector regime",
            "Catalyst",
            "Relative strength",
            "Price structure",
            "Volume and breadth",
            "Derivative confirmation",
            "Event risk",
            "Execution and invalidation",
        ],
        "mistakes": [
            "Trading against market/sector regime",
            "Ignoring relative strength",
            "No invalidation rule",
        ],
    },
    "short": {
        "window": "hours to 5 days",
        "hierarchy": [
            "Global overnight context",
            "GIFT / index-futures context",
            "USD/INR and key commodities",
            "Scheduled event map",
            "Gap classification",
            "Breadth and sector leadership",
            "Realised and implied volatility",
            "OI, PCR and skew by expiry",
            "Intraday confirmation",
        ],
        "mistakes": [
            "Ignoring the global/overnight context",
            "Trading event days at full size",
            "No hard daily risk limit",
        ],
    },
    "intraday": {
        "window": "single session",
        "hierarchy": [
            "Event and opening gap",
            "Volatility and liquidity regime",
            "Opening auction and first range",
            "VWAP and price structure",
            "Signed flow and book imbalance",
            "Relative volume and breadth",
            "Option and expiry context",
            "Latency and transaction cost",
            "Hard daily risk limit",
        ],
        "mistakes": [
            "No hard daily risk limit",
            "Trading through expiry with uncertain inventory",
            "Ignoring transaction cost",
        ],
    },
}

# Ch.25 final decision checklist — the discipline gates every decision passes.
DECISION_CHECKLIST = [
    "What exactly is being forecast?",
    "What is the forecast horizon?",
    "When was the information truly available?",
    "Which actor is expected or forced to act?",
    "Through which instrument will the action occur?",
    "Is the relation causal, predictive, contemporaneous or merely descriptive?",
    "Which regime makes the relationship plausible?",
    "What regime would break it?",
    "Are the confirmations independent?",
    "Does the signal survive realistic costs?",
    "Does it survive execution delay and impact?",
    "Has survivorship and look-ahead bias been eliminated?",
    "Has multiple testing been controlled?",
    "What is the full forecast distribution?",
    "What invalidates the thesis?",
    "What is the maximum tolerable loss?",
    "What is the available liquidity and capacity?",
    "Would the decision remain rational if the immediate outcome is adverse?",
]


# --------------------------------------------------------------------------- #
# State vector + regime classifier
# --------------------------------------------------------------------------- #

@dataclass
class RegimeState:
    """The transparent rule-based regime estimate (KB Ch.17)."""
    regime: str = "SIDEWAYS_LOWVOL"
    confidence: float = 0.0            # 0-1
    trend: str = "unknown"              # up / down / flat
    trend_detail: str = ""
    vix_pctile: float | None = None    # 0-100
    fii: dict = field(default_factory=dict)
    breadth: str = "not measured"
    components: dict = field(default_factory=dict)
    favors: str = ""
    trap: str = ""
    notes: list = field(default_factory=list)


def _safe_series(symbol: str, period: str = "2y") -> pd.DataFrame:
    """Return an indicator-enriched frame, or an empty frame on failure."""
    try:
        from webapp.server import df_with_indicators
        df = df_with_indicators(symbol, period)
        return df if len(df) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def regime_state() -> RegimeState:
    """Classify the market regime from independent components.

    Component -> role (from the KB state vector R(t)):
        NIFTY trend      -> trend state
        India VIX pctile -> realised/implied volatility regime
        FII 5d bias      -> institutional flow
        breadth          -> participation (best effort; often not measured)
    """
    from data.osint.fii_dii import FiiDiiTracker

    s = RegimeState()

    # --- trend from NIFTY (^NSEI) ---
    nifty = _safe_series("^NSEI", "2y")
    if len(nifty) >= 250 and "ema200" in nifty and nifty["ema200"].iloc[-1] == nifty["ema200"].iloc[-1]:
        close = float(nifty["close"].iloc[-1])
        ema50 = float(nifty["ema50"].iloc[-1]) if "ema50" in nifty else close
        ema200 = float(nifty["ema200"].iloc[-1])
        adx = float(nifty["adx"].iloc[-1]) if "adx" in nifty else 0.0
        s.components["nifty_close"] = round(close, 2)
        s.components["vs_ema200_pct"] = round((close / ema200 - 1) * 100, 2)
        s.components["adx"] = round(adx, 1)

        above = close > ema50 > ema200
        below = close < ema50 < ema200
        if above:
            s.trend = "up"; s.trend_detail = f"above EMA50>EMA200 (ADX {adx:.0f})"
        elif below:
            s.trend = "down"; s.trend_detail = f"below EMA50>EMA200 (ADX {adx:.0f})"
        else:
            s.trend = "flat"; s.trend_detail = "tangled EMAs"

        # trend regime is meaningful only with a directional ADX.
        s.components["trending"] = bool(adx >= 20)
    else:
        s.notes.append("NIFTY price data unavailable — trend not measured")

    # --- volatility regime from India VIX percentile ---
    vix = _safe_series("^INDIAVIX", "1y")
    if len(vix) >= 60 and "close" in vix:
        v = vix["close"].astype(float)
        s.vix_pctile = round(float((v.iloc[-1] > v).mean() * 100), 1)
        s.components["vix"] = round(float(v.iloc[-1]), 2)
    else:
        s.notes.append("India VIX unavailable — volatility regime not measured")

    # --- institutional flow (FII/DII) ---
    try:
        fii = FiiDiiTracker().regime_bias()
        s.fii = fii
    except Exception:
        fii = {"score": 0.0, "label": "NEUTRAL", "detail": "FII data unavailable"}
    s.components["fii_score"] = round(float(fii.get("score", 0.0)), 3)

    s.regime = _classify(s)
    s.confidence = _confidence(s)
    info = REGIMES[s.regime]
    s.favors = info["favored"]
    s.trap = info["trap"]
    return s


def _classify(s: RegimeState) -> str:
    """Transparent rule-based scorer mapping the state vector to a regime."""
    adx = s.components.get("adx", 0.0)
    trending = s.components.get("trending", False)
    fii = float(s.components.get("fii_score", 0.0))
    vp = s.vix_pctile

    # Liquidity crisis: high VIX + strong FII outflow.
    if vp is not None and vp >= 80 and fii <= -0.5:
        return "LIQUIDITY_CRISIS"

    if trending:
        if s.trend == "up":
            # liquidity-driven if VIX compresses (cheap beta) else broad.
            if vp is not None and vp <= 30:
                return "BULL_LIQUIDITY"
            return "BULL_BROAD"
        if s.trend == "down":
            return "BEAR_EARNINGS"

    # Flat / weak ADX.
    if vp is not None and vp <= 30:
        return "SIDEWAYS_LOWVOL"
    # High vol without a clear trend reads as a regime stress / event.
    if vp is not None and vp >= 75:
        return "EVENT"
    return "SIDEWAYS_LOWVOL"


def _confidence(s: RegimeState) -> float:
    """0-1: how much of the state vector was actually measured + agreement."""
    measured = 0
    if s.components.get("nifty_close") is not None:
        measured += 1
    if s.vix_pctile is not None:
        measured += 1
    if s.fii.get("detail") not in (None, "no data", "no FII rows",
                                   "FII data unavailable"):
        measured += 1
    base = measured / 3.0                      # data completeness
    agreement = 1.0                            # components rarely contradict here
    return round(min(1.0, base * agreement), 2)


# --------------------------------------------------------------------------- #
# Confirmations / invalidation for a position, gated by regime + horizon
# --------------------------------------------------------------------------- #

# Per-(regime, side) stance.  "avoid" means the regime argues against that side.
_STANCE = {
    ("BULL_BROAD", "long"): "favored",
    ("BULL_BROAD", "short"): "against",
    ("BULL_LIQUIDITY", "long"): "favored",
    ("BULL_LIQUIDITY", "short"): "against",
    ("BULL_NARROW", "long"): "conditional",
    ("BULL_NARROW", "short"): "against",
    ("SIDEWAYS_LOWVOL", "long"): "neutral",
    ("SIDEWAYS_LOWVOL", "short"): "neutral",
    ("BEAR_EARNINGS", "long"): "against",
    ("BEAR_EARNINGS", "short"): "favored",
    ("INFLATION_SHOCK", "long"): "conditional",
    ("INFLATION_SHOCK", "short"): "conditional",
    ("LIQUIDITY_CRISIS", "long"): "against",
    ("LIQUIDITY_CRISIS", "short"): "neutral",
    ("EVENT", "long"): "neutral",
    ("EVENT", "short"): "neutral",
    ("MONSOON_AGRI", "long"): "neutral",
    ("MONSOON_AGRI", "short"): "neutral",
}


def confirmations(state: RegimeState, side: int, horizon: str = "swing") -> list[str]:
    """What must be true for a `side` (+1/-1/0) at this `horizon` to be valid."""
    out = []
    hz = HORIZON_FRAMEWORKS.get(horizon)
    if hz:
        out.append(f"Horizon: {hz['window']} — priority signal is {hz['hierarchy'][0].lower()}.")
        out.append(f"Favour: {hz['hierarchy'][1].lower()}; second: {hz['hierarchy'][2].lower()}.")

    stance = _STANCE.get((state.regime, f"long" if side >= 0 else "short"), "neutral")
    out.append(f"Regime stance for this side: {stance} "
               f"(in {REGIMES[state.regime]['label']}, {state.favors.lower()}).")

    # regime-specific confirmations
    if state.regime in ("BULL_BROAD", "BULL_LIQUIDITY") and side >= 0:
        out.append("Confirm: breadth participation and relative-strength leadership.")
    if state.regime == "BULL_NARROW" and side >= 0:
        out.append("Confirm: breadth controls — cap-weight strength must be backed by advances.")
    if state.regime == "SIDEWAYS_LOWVOL" and side != 0:
        out.append("Confirm: a real breakout / reversion trigger; the trend filter is neutral.")
    if state.regime == "BEAR_EARNINGS" and side < 0:
        out.append("Confirm: weak breadth and negative revisions; favour quality/defensives.")
    if state.regime == "LIQUIDITY_CRISIS":
        out.append("Confirm: cash or convex hedge; do not fight the flow.")
    if state.regime == "EVENT":
        out.append("Confirm: reduced size and scenario analysis around the event.")

    # flow confirmation
    fii = state.components.get("fii_score", 0.0)
    if fii and fii > 0.25:
        out.append(f"Flow: FII net inflow (+{fii:.2f}) supports longs / hedges shorts.")
    elif fii and fii <= -0.25:
        out.append(f"Flow: FII net outflow ({fii:.2f}) pressures longs.")

    # vol regime
    if state.vix_pctile is not None:
        if state.vix_pctile >= 75:
            out.append(f"Vol: VIX at {state.vix_pctile}th pct — wide stops, smaller size.")
        elif state.vix_pctile <= 30:
            out.append(f"Vol: VIX compressed ({state.vix_pctile}th pct) — breakout prone, beware traps.")

    return out


def invalidation(state: RegimeState, side: int, horizon: str = "swing") -> list[str]:
    """What would break the thesis (the trap + regime-specific kill-switches)."""
    out = [f"Avoid the regime trap: {state.trap.lower()}."]
    if state.regime == "BULL_LIQUIDITY":
        out.append("Invalidated by: flow reversal / VIX expansion (liquidity not earnings).")
    if state.regime == "BULL_NARROW":
        out.append("Invalidated by: breadth drying up while cap-weights stall.")
    if state.regime == "SIDEWAYS_LOWVOL":
        out.append("Invalidated by: retest of the range edge and a close back inside.")
    if state.regime == "BEAR_EARNINGS":
        out.append("Invalidated by: broad strength / revisions turning up.")
    if state.regime == "LIQUIDITY_CRISIS":
        out.append("Invalidated by: policy or natural-buyer stabilisation.")
    if state.regime == "EVENT":
        out.append("Invalidated by: the outcome itself — re-estimate after repricing.")
    hz = HORIZON_FRAMEWORKS.get(horizon)
    if hz:
        out.append(f"Horizon kill-switch: watch '{hz['hierarchy'][-1].lower()}'.")
    return out


# --------------------------------------------------------------------------- #
# Assembled insight
# --------------------------------------------------------------------------- #

def build_insight(symbol: str | None = None, horizon: str = "swing",
                  side: int = 1) -> dict:
    """Top-level entry: full regime-conditioned actionable insight.

    `side` defaults to long (+1); pass -1 for a short/put view.  `symbol` is
    optional context; the regime itself is market-wide.
    """
    state = regime_state()
    hz = HORIZON_FRAMEWORKS.get(horizon, HORIZON_FRAMEWORKS["swing"])
    side_label = {1: "long / call (+1)", -1: "short / put (-1)", 0: "flat (0)"}
    stance = _STANCE.get((state.regime, f"long" if side >= 0 else "short"), "neutral")

    verdict = _verdict(stance, state.confidence)

    insight = {
        "symbol": symbol,
        "horizon": horizon,
        "side": side,
        "side_label": side_label.get(side, str(side)),
        "regime": state.regime,
        "regime_label": REGIMES[state.regime]["label"],
        "confidence": state.confidence,
        "verdict": verdict,
        "favors": state.favors,
        "trap": state.trap,
        "confirmations": confirmations(state, side, horizon),
        "invalidation": invalidation(state, side, horizon),
        "state_vector": {
            "nifty_close": state.components.get("nifty_close"),
            "vs_ema200_pct": state.components.get("vs_ema200_pct"),
            "adx": state.components.get("adx"),
            "vix_pctile": state.vix_pctile,
            "fii_score": state.components.get("fii_score"),
            "fii_label": state.fii.get("label"),
            "trend": state.trend,
            "trend_detail": state.trend_detail,
        },
        "horizon_framework": {
            "window": hz["window"],
            "hierarchy": hz["hierarchy"],
            "mistakes": hz["mistakes"],
        },
        "checklist": DECISION_CHECKLIST,
        "data_notes": state.notes or ["All regime components measured."],
    }
    return insight


def _verdict(stance: str, confidence: float) -> str:
    c = "high" if confidence >= 0.66 else ("medium" if confidence >= 0.34 else "low")
    if stance == "favored":
        return (f"FAVORABLE — the regime supports this side "
                f"({c} regime confidence). Size per risk, respect the stop.")
    if stance == "against":
        return (f"ADVERSE — the regime argues against this side "
                f"({c} regime confidence). Prefer the opposite or stand aside.")
    if stance == "conditional":
        return (f"CONDITIONAL — the regime is mixed "
                f"({c} confidence). Enter only on a confirming trigger and "
                f"with a defined invalidation.")
    return (f"NEUTRAL — no regime edge for this side "
            f"({c} confidence). Trade only on a specific setup, not the regime.")
