"""V10: inverse relative-ATR position sizing, with fixed bounded multipliers."""
import math
from E0V1E64_V5 import E0V1E64_V5


class E0V1E64_V10(E0V1E64_V5):
    def populate_indicators(self, dataframe, metadata):
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["r3_atr_pct"] = dataframe["atr"] / dataframe["close"]
        # 12h reference excludes even the latest completed bar; no future values.
        dataframe["r3_atr_reference"] = dataframe["r3_atr_pct"].rolling(
            144, min_periods=48).median().shift(1)
        return dataframe

    @staticmethod
    def volatility_multiplier(atr_pct, reference):
        if not (math.isfinite(atr_pct) and math.isfinite(reference)) or min(atr_pct, reference) <= 0:
            return 1.0
        return max(0.5, min(1.25, reference / atr_pct))

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        base = super().custom_stake_amount(pair, current_time, current_rate, proposed_stake,
                    min_stake, max_stake, leverage, entry_tag, side, **kwargs)
        frame = self.completed_frame(pair, current_time)
        if frame.empty:
            return base
        row = frame.iloc[-1]
        multiplier = self.volatility_multiplier(float(row["r3_atr_pct"]), float(row["r3_atr_reference"]))
        cap = min(proposed_stake, max_stake)
        if (min_stake or 0) > cap:
            return 0.0
        return self.bound_stake(base * multiplier, min_stake, cap)
