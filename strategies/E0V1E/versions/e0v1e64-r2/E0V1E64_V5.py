"""V5: selectively delay fastk exits, bounded by time and profit giveback."""
from research_common import ResearchBase


class E0V1E64_V5(ResearchBase):
    max_extension_minutes = 60

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        reason = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
        frame = self.completed_frame(pair, current_time)
        favorable = self.favorable_trend(frame, "short" if trade.is_short else "long")
        fastk_reasons = ("fastk_profit_cover", "fastk_profit_sell")
        state = trade.get_custom_data(key="v5_extension", default=None)
        if state is not None:
            peak = max(float(state["peak"]), current_profit)
            state["peak"] = peak
            trade.set_custom_data(key="v5_extension", value=state)
            # Observe callback profit, not future current-candle extrema.
            if current_profit <= max(0.002, peak * 0.5):
                return "v5_profit_floor"
            if (current_time.timestamp() - state["started"]) / 60 >= self.max_extension_minutes:
                return "v5_extension_timeout"
            if not favorable:
                return "v5_trend_end"
            return None if reason in fastk_reasons else reason
        if reason in fastk_reasons and favorable and 0.005 <= current_profit < 0.03:
            trade.set_custom_data(key="v5_extension", value={
                "started": current_time.timestamp(), "peak": current_profit})
            return None
        return reason
