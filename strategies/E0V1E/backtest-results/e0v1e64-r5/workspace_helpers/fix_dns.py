"""Monkey-patch DNS + mock CCXT exchanges for offline backtesting."""
import socket
import sys
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Part 1: Fix DNS resolution ────────────────────────────────────────
_original_getaddrinfo = socket.getaddrinfo

FIXES = {
    "www.okx.com": "54.46.25.13",
}


def _patched_getaddrinfo(host, port, family=socket.AF_UNSPEC,
                         type=socket.SOCK_STREAM, proto=0, flags=0):
    if host in FIXES and port == 443:
        host = FIXES[host]
    return _original_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _patched_getaddrinfo

# ── Part 2: Generic offline market data generator ───────────────────────
DATA_DIR = Path("/mnt/c/Users/why/Desktop/ft_userdata/user_data/data")


def _discover_pairs_from_data(exchange: str, trading_mode: str = "spot") -> list:
    """Discover available pairs from local data files."""
    pairs = set()
    data_path = DATA_DIR / exchange
    if trading_mode == "futures":
        data_path = data_path / "futures"

    if not data_path.exists():
        return []

    for f in data_path.glob("*5m*.feather"):
        name = f.stem  # e.g. BTC_USDT-5m or BTC_USDT_USDT-5m-futures
        # Parse base and quote from filename
        parts = name.split("-")[0].split("_")
        if len(parts) >= 2:
            base, quote = parts[0], parts[1]
            if trading_mode == "futures":
                pairs.add(f"{base}/{quote}:{quote}")
            else:
                pairs.add(f"{base}/{quote}")

    return sorted(pairs)


def _generate_spot_markets(pairs: list) -> list:
    """Generate spot market data for a list of pairs."""
    markets = []
    for pair in pairs:
        base, quote = pair.split("/")
        inst_id = f"{base}{quote}"
        markets.append({
            "id": inst_id,
            "symbol": pair,
            "base": base,
            "quote": quote,
            "settle": None,
            "baseId": base,
            "quoteId": quote,
            "settleId": None,
            "type": "spot",
            "spot": True,
            "margin": False,
            "swap": False,
            "future": False,
            "option": False,
            "active": True,
            "contract": False,
            "linear": None,
            "inverse": None,
            "taker": 0.001,
            "maker": 0.001,
            "contractSize": None,
            "expiry": None,
            "expiryDatetime": None,
            "strike": None,
            "optionType": None,
            "precision": {
                "amount": 1e-05,
                "price": 1e-08,
                "base": 8,
                "quote": 8,
            },
            "limits": {
                "leverage": {},
                "amount": {"min": 1e-05, "max": 90000000},
                "price": {"min": None, "max": None},
                "cost": {"min": 5.0, "max": None},
            },
            "info": {},
            "percentage": True,
            "tierBased": False,
            "feeSide": "get",
        })
    return markets


def _generate_futures_markets(pairs: list) -> list:
    """Generate futures/swap market data for a list of pairs."""
    markets = []
    for pair in pairs:
        # BTC/USDT:USDT -> base=BTC, quote=USDT, settle=USDT
        base, rest = pair.split("/")
        quote = rest.split(":")[0]
        settle = rest.split(":")[1] if ":" in rest else quote
        inst_id = f"{base}-{quote}-SWAP"
        markets.append({
            "id": inst_id,
            "symbol": pair,
            "base": base,
            "quote": quote,
            "settle": settle,
            "baseId": base,
            "quoteId": quote,
            "settleId": settle,
            "type": "swap",
            "spot": False,
            "margin": False,
            "swap": True,
            "future": False,
            "option": False,
            "active": True,
            "contract": True,
            "linear": True,
            "inverse": False,
            "taker": 0.0005,
            "maker": 0.0002,
            "contractSize": 0.01 if base == "BTC" else 0.1 if base in ("ETH", "BNB") else 1,
            "expiry": None,
            "expiryDatetime": None,
            "strike": None,
            "optionType": None,
            "precision": {
                "amount": 0.001,
                "price": 0.1 if base == "BTC" else 0.01 if base in ("ETH", "BNB") else 0.001,
                "base": 8,
                "quote": 8,
            },
            "limits": {
                "leverage": {"min": 1, "max": 100},
                "amount": {"min": 0.001, "max": 1000000},
                "price": {"min": None, "max": None},
                "cost": {"min": 0.1, "max": None},
            },
            "info": {},
            "percentage": True,
            "tierBased": True,
            "feeSide": "get",
        })
    return markets


# ── Part 3: Generic CCXT monkey-patch for offline exchanges ─────────────
_PATCHED_EXCHANGES = set()


def _patch_exchange(exchange_name: str):
    """Monkey-patch a CCXT exchange to use locally discovered markets."""
    if exchange_name in _PATCHED_EXCHANGES:
        return
    _PATCHED_EXCHANGES.add(exchange_name)

    try:
        import ccxt.async_support as ccxt_async
        # In CCXT, the module IS the class (e.g. ccxt.async_support.okx IS okx class)
        ex_class = getattr(ccxt_async, exchange_name, None)
        if ex_class is None or not isinstance(ex_class, type):
            return

        # Try to discover pairs from local data, fall back to common pairs
        pairs_futures = _discover_pairs_from_data(exchange_name, "futures")
        pairs_spot = _discover_pairs_from_data(exchange_name, "spot")

        # Use all discovered pairs; if data exists, use those pairs for both modes
        all_pairs = list(set(pairs_futures + pairs_spot))

        # If no data files found, provide a generous set of common pairs
        # so that download-data and backtesting both work
        if not all_pairs:
            all_pairs = [
                f"{b}/{q}" for b, q in [
                    ("BTC", "USDT"), ("ETH", "USDT"), ("BNB", "USDT"),
                    ("ADA", "USDT"), ("SOL", "USDT"), ("DOT", "USDT"),
                    ("LINK", "USDT"), ("XRP", "USDT"), ("LTC", "USDT"),
                    ("BCH", "USDT"), ("ETC", "USDT"), ("ALGO", "USDT"),
                    ("DOGE", "USDT"), ("AVAX", "USDT"), ("MATIC", "USDT"),
                    ("UNI", "USDT"), ("ATOM", "USDT"), ("FIL", "USDT"),
                    ("APT", "USDT"), ("ARB", "USDT"), ("OP", "USDT"),
                    ("NEAR", "USDT"), ("INJ", "USDT"), ("TIA", "USDT"),
                    ("SUI", "USDT"), ("SEI", "USDT"), ("RUNE", "USDT"),
                ]
            ]

        # Generate both spot and futures markets
        spot_markets = _generate_spot_markets(
            [p for p in all_pairs if ":" not in p])
        futures_markets = _generate_futures_markets(
            [p for p in all_pairs if ":" in p])

        # Always provide both spot and futures markets
        spot_common = [p for p in all_pairs if ":" not in p]
        futures_common = [p for p in all_pairs if ":" in p]

        # Also generate futures equivalents for spot-only pairs
        # and spot equivalents for futures-only pairs
        extra_futures = [f"{p}:USDT" for p in spot_common if f"{p}:USDT" not in futures_common]
        futures_common.extend(extra_futures)

        spot_markets = _generate_spot_markets(spot_common)
        futures_markets = _generate_futures_markets(futures_common)

        # Combine all markets so both spot and futures pairs are available
        markets_data = spot_markets + futures_markets

        logger.info(f"[fix_dns] Patching {exchange_name}: {len(markets_data)} pairs "
                    f"(spot={len(spot_markets)}, futures={len(futures_markets)})")

        # Patch async load_markets
        _orig_load_markets = ex_class.load_markets

        async def _patched_load_markets(self, reload=False, params={}):
            self.markets = {m['symbol']: m for m in markets_data}
            self.markets_by_id = {m['id']: m for m in markets_data}
            self.markets_loading = None
            return list(self.markets.values())

        ex_class.load_markets = _patched_load_markets

        # OKX exposes leverage tiers one market at a time.  Backtests only
        # need a valid deterministic ceiling and maintenance rate; fetching
        # hundreds of live tiers makes offline validation slow and can leave
        # an empty cache when concurrent runs race or the network is absent.
        async def _patched_fetch_market_leverage_tiers(self, symbol, params={}):
            return [{
                "tier": 1,
                "symbol": symbol,
                "minNotional": 0.0,
                "maxNotional": 1_000_000_000.0,
                "maintenanceMarginRate": 0.005,
                "maxLeverage": 100.0,
                "info": {},
            }]

        ex_class.fetch_market_leverage_tiers = _patched_fetch_market_leverage_tiers

        # Also patch sync version
        import ccxt
        sync_class = getattr(ccxt, exchange_name, None)
        if sync_class and isinstance(sync_class, type):
            sync_class.load_markets = lambda self, reload=False, params={}: markets_data
            sync_class.fetch_market_leverage_tiers = (
                lambda self, symbol, params={}: [{
                    "tier": 1,
                    "symbol": symbol,
                    "minNotional": 0.0,
                    "maxNotional": 1_000_000_000.0,
                    "maintenanceMarginRate": 0.005,
                    "maxLeverage": 100.0,
                    "info": {},
                }]
            )

    except Exception as e:
        logger.warning(f"[fix_dns] Failed to patch {exchange_name}: {e}")


# Patch all exchanges for which we have local data
for _ex in DATA_DIR.iterdir():
    if _ex.is_dir():
        _patch_exchange(_ex.name)

print(f"[fix_dns] DNS fix + offline markets active. "
      f"Patched exchanges: {sorted(_PATCHED_EXCHANGES)}", file=sys.stderr)
