"""Central configuration for the Indian Markets Trading System."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------------ #
# Zerodha Kite Connect (fill .env when you have your API key)
# ------------------------------------------------------------------ #
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")

TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()  # paper | live

CAPITAL = float(os.getenv("CAPITAL", 500_000))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 1.0))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", 10))

# ------------------------------------------------------------------ #
# Instrument universes (NSE symbols)
# ------------------------------------------------------------------ #
NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO",
    "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC", "INDUSINDBK",
    "INFY", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

NIFTYNEXT50_SWING = [
    "ABB", "ADANIGREEN", "AMBUJACEM", "BANKBARODA", "BPCL", "BOSCHLTD",
    "BRITANNIA", "CANBK", "CHOLAFIN", "DABUR", "DIVISLAB", "DLF",
    "DMART", "GAIL", "GODREJCP", "HAVELLS", "HAL", "ICICIGI",
    "INDIGO", "IOC", "INDHOTEL", "IRFC", "JINDALSTEL", "JSWENERGY",
    "LICI", "LTIM", "MOTHERSON", "NAUKRI", "PIDILITIND", "PFC",
    "PNB", "RECLTD", "SHREECEM", "SIEMENS", "SAIL", "TATAPOWER",
    "TORNTPHARM", "TVSMOTOR", "VEDL", "ZOMATO", "ZYDUSLIFE",
]

SWING_UNIVERSE = sorted(set(NIFTY50 + NIFTYNEXT50_SWING))

HIGH_LIQ_FNO = [s for s in NIFTY50]  # F&O-eligible liquid names

INDICES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY MIDCAP 100": "^NSEMDCP50",
    "SENSEX": "^BSESN",
    "INDIA VIX": "^INDIAVIX",
}

COMMODITY_MCX = ["GOLD", "SILVER", "CRUDEOIL", "COPPER", "ZINC", "NATURALGAS"]
CURRENCY_CDS = ["USDINR", "EURINR", "GBPINr".upper(), "JPYINR"]

# ------------------------------------------------------------------ #
# Backtest / strategy defaults
# ------------------------------------------------------------------ #
BACKTEST_START = "2018-01-01"
BACKTEST_END = None          # today
BENCHMARK = "^NSEI"          # Nifty 50

RISK_FREE_RATE = 0.065       # ~ India 10y GSec / T-bill blend
TRADING_DAYS = 252

STOP_LOSS_ATR_MULT = 2.0
TARGET_RR = 2.0              # reward:risk default for swing trades
