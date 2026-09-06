"""V1: direction-correct short adverse excursion and CCI recovery exit."""
from research_common import ResearchBase


class E0V1E64_V1(ResearchBase):
    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if not trade.is_short:
            return super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
        frame = self.completed_frame(pair, current_time)
        if frame.empty:
            return None
        # Freqtrade writes the current backtest candle high into max_rate
        # BEFORE custom_exit. Use only completed candles and observed rate.
        state = trade.get_custom_data(key="v1_adverse", default={}) or {}
        worst_rate = max(float(state.get("worst_rate", trade.open_rate)),
                         trade.open_rate, current_rate)
        eligible = frame.loc[frame["date"] >= trade.open_date_utc]
        last_date = state.get("last_date", "")
        if last_date:
            eligible = eligible.loc[eligible["date"].astype(str) > last_date]
        if not eligible.empty:
            worst_rate = max(worst_rate, float(eligible["high"].max()))
        trade.set_custom_data(key="v1_adverse", value={
            "worst_rate": worst_rate, "last_date": str(frame.iloc[-1]["date"])})
        candle = frame.iloc[-1]
        if current_profit > 0 and candle["fastk"] < self.short_fastk.value:
            return "fastk_profit_cover"
        if (trade.calc_profit_ratio(worst_rate) <= -0.10
                and current_profit > self.short_cci_profit.value
                and candle["cci"] < self.short_cci.value):
            return "v1_cci_loss_cover"
        return None
