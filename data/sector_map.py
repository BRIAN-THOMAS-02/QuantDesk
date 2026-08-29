"""Static NIFTY sector map for the universe (used by the heatmap page).

The live data feed does not carry a sector tag, so this curated map assigns
each instrument in the swing universe to a Nifty 50 sector group.  Unknown
symbols fall through to "OTHER".  This is a display aid only — it carries no
trading meaning and must not influence signal generation.
"""
from __future__ import annotations

SECTOR_MAP: dict[str, list[str]] = {
    "Banking": [
        "AXISBANK", "BANKBARODA", "CANBK", "HDFCBANK", "ICICIBANK",
        "INDUSINDBK", "KOTAKBANK", "PNB", "SBIN"],
    "Financials / NBFC / Insurance": [
        "BAJAJFINSV", "BAJFINANCE", "CHOLAFIN", "HDFCLIFE", "ICICIGI",
        "IRFC", "JIOFIN", "LICI", "PFC", "SBILIFE", "SHRIRAMFIN"],
    "Energy & Power": [
        "BPCL", "COALINDIA", "GAIL", "IOC", "JSWENERGY", "NTPC",
        "ONGC", "POWERGRID", "TATAPOWER"],
    "Metals & Mining": [
        "HINDALCO", "JINDALSTEL", "SAIL", "TATASTEEL", "VEDL"],
    "IT": [
        "HCLTECH", "INFY", "LTIM", "NAUKRI", "TECHM", "WIPRO"],
    "Auto & Mobility": [
        "BAJAJ-AUTO", "BOSCHLTD", "EICHERMOT", "HEROMOTOCO", "MARUTI",
        "MOTHERSON", "TATAMOTORS", "TVSMOTOR"],
    "Cement & Construction": [
        "AMBUJACEM", "GRASIM", "SHREECEM", "ULTRACEMCO"],
    "Pharma & Health": [
        "APOLLOHOSP", "CIPLA", "DIVISLAB", "DRREDDY", "SUNPHARMA",
        "TORNTPHARM", "ZYDUSLIFE"],
    "FMCG & Consumer": [
        "BRITANNIA", "DABUR", "GODREJCP", "HINDUNILVR", "ITC",
        "NESTLEIND", "PIDILITIND", "TATACONSUM", "TRENT"],
    "Capital Goods / Infra / Defence": [
        "ABB", "BEL", "HAL", "HAVELLS", "LT", "RECLTD", "SIEMENS"],
    "Aditya Birla Group": [
        "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ETERNAL"],
    "Other / Diversified": [
        "RELIANCE", "BHARTIARTL", "DMART", "DLF", "INDHOTEL",
        "INDIGO", "TITAN", "ZOMATO"],
}

_NAME_TO_SECTOR: dict[str, str] = {
    n: s for s, names in SECTOR_MAP.items() for n in names
}


def sector_of(symbol: str) -> str:
    """Return the sector group for an NSE instrument (root-normalised)."""
    root = str(symbol).upper().replace(".NS", "").replace(".BO", "").lstrip(".")
    if root in ("NSEI", "NSEBANK", "CNXIT", "NSEMDCP50"):
        return "Index"
    return _NAME_TO_SECTOR.get(root, "OTHER")


def sector_groups() -> dict[str, list[str]]:
    """Return a copy of the sector map (defensive)."""
    return {k: list(v) for k, v in SECTOR_MAP.items()}
