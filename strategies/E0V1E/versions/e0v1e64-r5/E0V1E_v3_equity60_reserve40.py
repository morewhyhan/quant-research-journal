"""Research variant: 60% base exposure with a 40% drawdown reserve.

This strategy inherits every signal and exit rule from the live E0V1E_v3.
Only position sizing changes.  It is intentionally kept separate from the
server strategy and must not be deployed before restart-persistence is added.
"""

from datetime import datetime

from E0V1E_v3 import E0V1E_v3


class E0V1E_v3_equity60_reserve40(E0V1E_v3):
    # The live config makes 97% of the wallet tradable.  These levels refer to
    # the whole-wallet exposure used in the mathematical replay.
    tradable_balance_ratio = 0.97
    base_fraction = 0.60
    reserve_step = 0.133333

    _peak_tradable_balance = None

    def bot_start(self, **kwargs) -> None:
        self._peak_tradable_balance = None

    @classmethod
    def fraction_for_drawdown(cls, drawdown: float) -> float:
        """Deploy the reserve in three steps as realized equity draws down."""
        if drawdown < 0.05:
            return cls.base_fraction
        if drawdown < 0.10:
            return cls.base_fraction + cls.reserve_step
        if drawdown < 0.20:
            return cls.base_fraction + 2 * cls.reserve_step
        return cls.tradable_balance_ratio

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        if self.wallets is None:
            return proposed_stake * (self.base_fraction / self.tradable_balance_ratio)

        current_balance = self.wallets.get_total_stake_amount()
        if self._peak_tradable_balance is None or current_balance > self._peak_tradable_balance:
            self._peak_tradable_balance = current_balance

        drawdown = max(0.0, 1.0 - current_balance / self._peak_tradable_balance)
        target_fraction = self.fraction_for_drawdown(drawdown)

        # proposed_stake is the 97%-tradable all-in amount with max_open_trades=1.
        stake = proposed_stake * (target_fraction / self.tradable_balance_ratio)
        if min_stake is not None:
            stake = max(stake, min_stake)
        return min(stake, max_stake)
