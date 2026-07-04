"""
MeanRevertFilter - Custom FreqTrade pairlist filter.

Filters out pairs with extreme funding rates (asymmetric thresholds):
  - Positive funding (longs pay): reject if > 1% (FOMO, costly to hold)
  - Negative funding (shorts pay): reject if < -3% (extreme panic only)

Negative funding is good for long positions (you get paid), so we're more lenient.
Volatility filtering is handled by VolatilityFilter.
"""

import logging
from typing import List

from freqtrade.plugins.pairlist.IPairList import IPairList, PairlistParameter, SupportsBacktesting

logger = logging.getLogger(__name__)


class MeanRevertFilter(IPairList):

    is_pairlist_generator = False
    supports_backtesting = SupportsBacktesting.NO

    @staticmethod
    def description() -> str:
        return "Filter pairs by funding rate (asymmetric: shorts OK, longs strict)."

    @staticmethod
    def available_parameters() -> dict[str, PairlistParameter]:
        return {
            "max_positive_funding_rate": {
                "description": "Max positive funding rate (longs pay shorts)",
                "help": "Positive rate = longs pay. Reject if above (e.g. 0.01 = 1%).",
                "type": "number",
                "default": 0.01,
            },
            "max_negative_funding_rate": {
                "description": "Max negative funding rate magnitude (shorts pay longs)",
                "help": "Negative rate = shorts pay you. More lenient (e.g. 0.03 = 3%).",
                "type": "number",
                "default": 0.03,
            },
        }

    def __init__(self, exchange, pairlistmanager, config, pairlistconfig, pairlist_pos):
        super().__init__(exchange, pairlistmanager, config, pairlistconfig, pairlist_pos)
        self._max_positive = pairlistconfig.get("max_positive_funding_rate", 0.01)
        self._max_negative = pairlistconfig.get("max_negative_funding_rate", 0.03)

    @property
    def needstickers(self) -> bool:
        return False

    def short_desc(self) -> str:
        return (
            f"{self.__class__.__name__}: "
            f"LongPay<{self._max_positive:.1%}, "
            f"ShortPay<{self._max_negative:.1%}"
        )

    def _get_funding_rate(self, pair: str):
        try:
            rate = self._exchange.fetch_funding_rate(pair)
            if isinstance(rate, dict):
                return float(rate.get("fundingRate", 0))
            elif isinstance(rate, (int, float)):
                return float(rate)
            return 0.0
        except Exception:
            return None

    def filter_pairlist(self, pairlist: List[str], tickers=None) -> List[str]:
        result = []
        rejected_long = 0
        rejected_short = 0
        for pair in pairlist:
            try:
                funding = self._get_funding_rate(pair)
                if funding is None:
                    result.append(pair)
                    continue

                if funding > 0 and funding > self._max_positive:
                    logger.info(
                        f"MeanRevertFilter: {pair} rejected - "
                        f"longs pay {funding:.4%} (max {self._max_positive:.1%})"
                    )
                    rejected_long += 1
                    continue

                if funding < 0 and abs(funding) > self._max_negative:
                    logger.info(
                        f"MeanRevertFilter: {pair} rejected - "
                        f"shorts pay {abs(funding):.4%} (max {self._max_negative:.1%})"
                    )
                    rejected_short += 1
                    continue

                result.append(pair)
            except Exception as e:
                logger.debug(f"MeanRevertFilter: {pair} error: {e}, keeping")
                result.append(pair)
        logger.info(
            f"MeanRevertFilter: {len(result)} passed, "
            f"{rejected_long} rejected (longs pay), "
            f"{rejected_short} rejected (shorts pay)"
        )
        return result

    def _gen_pairlist(self, pairlist: List[str], tickers=None) -> List[str]:
        return pairlist
