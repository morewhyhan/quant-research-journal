"""V17: V5 drawdown reserve requires a currently qualified directional signal."""
import math

from E0V1E64_V5 import E0V1E64_V5
from r4_common import R4ResearchMixin


class E0V1E64_V17(R4ResearchMixin, E0V1E64_V5):
    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        target_fraction = self.base_fraction
        if self.wallets is not None:
            balance = self.wallets.get_total_stake_amount()
            if not math.isfinite(balance) or balance <= 0:
                return 0.0
            if self._peak_tradable_balance is None or balance > self._peak_tradable_balance:
                self._peak_tradable_balance = balance
            drawdown = max(0.0, 1.0 - balance / self._peak_tradable_balance)
            frame = self.r4_completed_frame(pair, current_time)
            if not frame.empty:
                row = frame.iloc[-1]
                other = "short" if side == "long" else "long"
                signal = (side in ("long", "short")
                          and row.get("enter_" + side, 0) == 1
                          and row.get("enter_" + other, 0) != 1
                          and row.get("exit_" + side, 0) != 1)
                if signal and self.strong_trend(frame, side):
                    target_fraction = self.fraction_for_drawdown(drawdown)
        stake = proposed_stake * target_fraction / self.tradable_balance_ratio
        if not all(math.isfinite(x) for x in (stake, proposed_stake, max_stake)):
            return 0.0
        stake = min(stake, proposed_stake, max_stake)
        # Never inflate the planned budget just to meet the exchange minimum.
        if stake <= 0 or (min_stake is not None and stake < min_stake):
            return 0.0
        return stake
