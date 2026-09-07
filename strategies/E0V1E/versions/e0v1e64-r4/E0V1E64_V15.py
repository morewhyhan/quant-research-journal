"""V15: allow strong >=3% winners into V5's existing bounded extension."""
from E0V1E64_V5 import E0V1E64_V5
from r4_common import R4ResearchMixin


class E0V1E64_V15(R4ResearchMixin, E0V1E64_V5):
    large_winner_threshold = 0.03

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # V5 still owns all original exits, active-state peak/floor and the 60m limit.
        reason = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
        if trade.get_custom_data(key="v5_extension", default=None) is not None:
            return reason
        if (reason not in ("fastk_profit_cover", "fastk_profit_sell")
                or current_profit < self.large_winner_threshold):
            return reason
        frame = self.r4_completed_frame(pair, current_time)
        if not self.strong_trend(frame, "short" if trade.is_short else "long"):
            return reason
        trade.set_custom_data(key="v5_extension", value={
            "started": current_time.timestamp(), "peak": current_profit,
        })
        # The original custom stop/ROI retain priority; no stop is loosened here.
        return None
