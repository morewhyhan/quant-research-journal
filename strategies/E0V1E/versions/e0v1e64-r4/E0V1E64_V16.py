"""V16: exit a sustained failed rebound, not every trade briefly down 6%."""
from datetime import timedelta
import math

import pandas as pd

from E0V1E64_V5 import E0V1E64_V5
from r4_common import R4ResearchMixin


class E0V1E64_V16(R4ResearchMixin, E0V1E64_V5):
    failure_loss_threshold = -0.06
    failure_min_age_minutes = 120
    failure_rebound_bars = 12  # one hour continuously on the wrong side of the 2h MA
    failure_trend_bars = 3    # three completed confirmations of the longer trend

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        reason = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
        if reason:
            return reason
        if (not math.isfinite(current_profit) or current_profit > self.failure_loss_threshold
                or current_time - trade.open_date_utc < timedelta(minutes=self.failure_min_age_minutes)):
            return None
        frame = self.r4_completed_frame(pair, current_time)
        tail = frame.tail(self.failure_rebound_bars)
        if (len(tail) < self.failure_rebound_bars
                or tail.iloc[0]["date"] < trade.open_date_utc
                or not tail["date"].diff().iloc[1:].eq(pd.Timedelta(minutes=5)).all()):
            return None
        columns = ["close", "ma240", "r4_ma_2h", "r4_ma_2h_old"]
        if any(not tail[col].map(math.isfinite).all() for col in columns):
            return None
        direction = -1 if trade.is_short else 1
        no_recovery = (direction * (tail["close"] - tail["r4_ma_2h"]) < 0).all()
        recent = tail.tail(self.failure_trend_bars)
        trend_failed = ((direction * (recent["close"] - recent["ma240"]) < 0)
                        & (direction * (recent["r4_ma_2h"] - recent["r4_ma_2h_old"]) < 0)).all()
        if no_recovery and trend_failed:
            return "v16_failed_rebound_short" if trade.is_short else "v16_failed_rebound_long"
        return None
