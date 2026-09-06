"""V4: modest signal-specific multipliers on the existing drawdown ladder."""
from research_common import ResearchBase


class E0V1E64_V4(ResearchBase):
    signal_multipliers = {"short_1": 0.90, "short_new": 1.10,
                          "buy_1": 1.0, "buy_new": 1.0}

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        stake = super().custom_stake_amount(
            pair, current_time, current_rate, proposed_stake, min_stake,
            max_stake, leverage, entry_tag, side, **kwargs)
        tag = str(entry_tag or "")
        # Concatenated short tags use the conservative short_1 multiplier.
        multiplier = self.signal_multipliers.get(tag, 0.90 if "short_1" in tag else 1.0)
        return self.bound_stake(min(stake * multiplier, proposed_stake), min_stake, max_stake)
