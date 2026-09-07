"""V14: rank simultaneous V5 signals without adding slots or changing exits."""
import logging
import math

import pandas as pd

from E0V1E64_V5 import E0V1E64_V5
from r4_common import R4ResearchMixin, closed_bar_time

logger = logging.getLogger(__name__)


class E0V1E64_V14(R4ResearchMixin, E0V1E64_V5):
    trend_weight = 0.50
    strength_weight = 0.30
    liquidity_weight = 0.20

    def __init__(self, config):
        super().__init__(config)
        self._rank_frames = {}
        self._rank_key = None
        self._ranked = []

    def bot_start(self, **kwargs):
        super().bot_start(**kwargs)
        self._rank_frames.clear()
        self._rank_key = None
        self._ranked = []

    def populate_exit_trend(self, dataframe, metadata):
        frame = super().populate_exit_trend(dataframe, metadata)
        # Match the engine's per-pair startup trimming. Otherwise a newly listed
        # pair could win the ranking before the engine allows it to trade.
        self._store_rank_frame(metadata["pair"], frame.iloc[self.startup_candle_count:])
        return frame

    def _store_rank_frame(self, pair, frame):
        """Engine computes all pair signals before iterating entries in backtests.

        Keep only ranking fields, BEFORE the engine shifts signals. Full history
        is stored, but ranked_signals reads exactly one completed timestamp.
        This avoids pair-iteration-dependent DataProvider slices.
        """
        if frame.empty:
            self._rank_frames.pop(pair, None)
        else:
            slim = frame[["date", "r4_return_4h", "r4_quote_volume_1h"]].copy()
            for col in ("enter_long", "enter_short", "exit_long", "exit_short",
                        "r4_trend_long", "r4_trend_short"):
                slim[col] = frame[col].eq(1) if col in frame else False
            slim = slim.set_index("date").sort_index()
            if not slim.index.is_unique:
                raise ValueError("V14 requires unique candle timestamps: " + pair)
            self._rank_frames[pair] = slim
        self._rank_key = None

    def ranked_signals(self, current_time):
        cutoff = closed_bar_time(current_time)
        whitelist = tuple(sorted(self.dp.current_whitelist()))
        key = (cutoff, whitelist)
        if key == self._rank_key:
            return self._ranked
        rows = {}
        for pair in whitelist:
            frame = self._rank_frames.get(pair)
            if frame is None or cutoff not in frame.index:
                continue
            row = frame.loc[cutoff]
            if math.isfinite(float(row["r4_return_4h"])):
                rows[pair] = row
        # Only pairs with data at this very timestamp enter the market proxy.
        market_return = pd.Series([r["r4_return_4h"] for r in rows.values()], dtype=float).median()
        candidates = []
        for pair, row in rows.items():
            liquidity = float(row["r4_quote_volume_1h"])
            if not math.isfinite(liquidity) or liquidity <= 0:
                continue
            for side, other, direction in (("long", "short", 1), ("short", "long", -1)):
                if (row["enter_" + side] and not row["enter_" + other]
                        and not row["exit_" + side]):
                    candidates.append({
                        "pair": pair, "side": side,
                        "trend": float(row["r4_trend_" + side]),
                        "strength": direction * (float(row["r4_return_4h"]) - market_return),
                        "liquidity": liquidity,
                    })
        if candidates:
            table = pd.DataFrame(candidates)
            table["score"] = (self.trend_weight * table["trend"]
                              + self.strength_weight * table["strength"].rank(pct=True)
                              + self.liquidity_weight * table["liquidity"].rank(pct=True))
            table = table.sort_values(["score", "pair", "side"], ascending=[False, True, True])
            self._ranked = table.to_dict("records")
        else:
            self._ranked = []
        self._rank_key = key
        return self._ranked

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        try:
            ranked = self.ranked_signals(current_time)
            winner = next((row for row in ranked if not self.is_pair_locked(
                row["pair"], candle_date=closed_bar_time(current_time).to_pydatetime(),
                side=row["side"])), None)
            if winner is None or (pair, side) != (winner["pair"], winner["side"]):
                return False
        except Exception:
            # Freqtrade's entry callback wrapper otherwise defaults to True on errors.
            logger.exception("V14 ranking failed; refusing this entry.")
            return False
        return super().confirm_trade_entry(pair, order_type, amount, rate, time_in_force,
                                           current_time, entry_tag, side, **kwargs)
