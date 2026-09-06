"""V3: drawdown reserve requires favorable trend and normal volatility."""
from research_common import ResearchBase


class E0V1E64_V3(ResearchBase):
    def populate_indicators(self, dataframe, metadata):
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["v3_atr_pct"] = dataframe["atr"] / dataframe["close"]
        dataframe["v3_atr_reference"] = dataframe["v3_atr_pct"].shift(1).rolling(48).median()
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        stake = super().custom_stake_amount(
            pair, current_time, current_rate, proposed_stake, min_stake,
            max_stake, leverage, entry_tag, side, **kwargs)
        frame = self.completed_frame(pair, current_time)
        normal = (not frame.empty
            and frame.iloc[-1]["v3_atr_pct"] <= 1.5 * frame.iloc[-1]["v3_atr_reference"])
        if normal and self.favorable_trend(frame, side):
            return stake
        cap = proposed_stake * self.base_fraction / self.tradable_balance_ratio
        return self.bound_stake(min(stake, cap), min_stake, max_stake)
