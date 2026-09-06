"""V2: exit stale losing short_1 after four hours and failed recovery."""
from research_common import ResearchBase


class E0V1E64_V2(ResearchBase):
    stale_minutes = 240
    stale_loss = -0.03

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        reason = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
        if reason:
            return reason
        elapsed = (current_time - trade.open_date_utc).total_seconds() / 60
        if (not trade.is_short or "short_1" not in str(trade.enter_tag)
                or elapsed < self.stale_minutes or current_profit > self.stale_loss):
            return None
        frame = self.completed_frame(pair, current_time)
        if len(frame) >= 13 and frame.iloc[-1]["close"] >= frame.iloc[-13]["close"]:
            return "v2_stale_short_4h"
        return None
