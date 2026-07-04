"""
SpotVolumePairList - Generate pairlist from spot market volume ranking,
then map to corresponding futures pairs.

Rationale: Large-cap coins (ranked by spot volume) behave more predictably
for mean-reversion strategies than futures-only meme coins.
"""

import logging
from typing import List, Optional
from datetime import timedelta

import ccxt
from freqtrade.plugins.pairlist.IPairList import IPairList, PairlistParameter, SupportsBacktesting

logger = logging.getLogger(__name__)


class SpotVolumePairList(IPairList):
    """Pairlist: rank spot pairs by volume, map to available futures."""

    is_pairlist_generator = True
    supports_backtesting = SupportsBacktesting.NO

    @staticmethod
    def description() -> str:
        return "Rank spot pairs by volume, convert to futures, return top N."

    @staticmethod
    def available_parameters() -> dict[str, PairlistParameter]:
        return {
            "number_assets": {
                "description": "Number of futures pairs to return",
                "type": "number",
                "default": 250,
            },
            "refresh_period": {
                "description": "Refresh period in hours",
                "type": "number",
                "default": 24,
            },
        }

    def __init__(self, exchange, pairlistmanager, config, pairlistconfig, pairlist_pos):
        super().__init__(exchange, pairlistmanager, config, pairlistconfig, pairlist_pos)
        self._num = pairlistconfig.get("number_assets", 250)
        self._refresh_hours = pairlistconfig.get("refresh_period", 24)
        self._spot_exchange: Optional[ccxt.Exchange] = None
        self._last_refresh = None
        self._cached_pairs: List[str] = []

    @property
    def needstickers(self) -> bool:
        return False

    def short_desc(self) -> str:
        return f"{self.__class__.__name__}: spot top {self._num} -> futures"

    def _get_spot_exchange(self):
        """Create a spot-only CCXT exchange instance for fetching spot volume data."""
        if self._spot_exchange is None:
            # Copy config but use spot market type
            exchange_config = self._exchange._config.copy()
            spot_ccxt = {
                'apiKey': '',
                'secret': '',
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
            }
            self._spot_exchange = getattr(ccxt, 'okx')(spot_ccxt)
            self._spot_exchange.load_markets()
            logger.info("SpotVolumePairList: spot exchange initialized")
        return self._spot_exchange

    def _needs_refresh(self) -> bool:
        if self._last_refresh is None:
            return True
        elapsed = self._pairlistmanager._last_refresh or 0
        # Check if enough time has passed
        import time
        return (time.time() - self._last_refresh) > (self._refresh_hours * 3600)

    def _gen_pairlist(self, pairlist: List[str], tickers=None) -> List[str]:
        """Generate pairlist from spot volume ranking, mapped to futures."""
        if not self._needs_refresh() and self._cached_pairs:
            logger.debug(f"SpotVolumePairList: using cached {len(self._cached_pairs)} pairs")
            return self._cached_pairs

        try:
            spot_ex = self._get_spot_exchange()
        except Exception as e:
            logger.warning(f"SpotVolumePairList: failed to init spot exchange: {e}")
            # Fall back to cached or empty
            return self._cached_pairs or pairlist

        # Get spot tickers sorted by volume
        try:
            spot_tickers = spot_ex.fetch_tickers()
        except Exception as e:
            logger.warning(f"SpotVolumePairList: failed to fetch spot tickers: {e}")
            return self._cached_pairs or pairlist

        # Rank by quote volume (USDT volume)
        ranked = []
        for symbol, ticker in spot_tickers.items():
            if not symbol.endswith('/USDT'):
                continue
            vol = ticker.get('quoteVolume') or ticker.get('baseVolume', 0) or 0
            try:
                vol = float(vol)
            except (ValueError, TypeError):
                vol = 0
            ranked.append((symbol, vol))

        ranked.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"SpotVolumePairList: ranked {len(ranked)} spot USDT pairs by volume")

        # Get available futures markets from the main exchange
        futures_markets = {
            s for s, m in self._exchange.markets.items()
            if m.get('swap') and m.get('quote') == 'USDT' and m.get('active')
        }

        # Map spot -> futures, keep top N
        result = []
        for spot_sym, vol in ranked:
            base = spot_sym.split('/')[0]
            futures_sym = f"{base}/USDT:USDT"
            if futures_sym in futures_markets and futures_sym not in result:
                result.append(futures_sym)
            if len(result) >= self._num:
                break

        import time
        self._last_refresh = time.time()
        self._cached_pairs = result

        logger.info(
            f"SpotVolumePairList: generated {len(result)} futures pairs "
            f"from top {self._num} spot pairs (scanned {len(ranked)} spot)"
        )
        return result

    def filter_pairlist(self, pairlist: List[str], tickers=None) -> List[str]:
        """Return the generated pairlist (this is a generator, not a filter)."""
        return self._gen_pairlist(pairlist, tickers)
