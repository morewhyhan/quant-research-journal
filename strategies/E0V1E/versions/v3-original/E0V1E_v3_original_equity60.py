"""Research-only hybrid: V3 Original risk logic plus a 60/40 equity reserve."""

from datetime import datetime

from E0V1E_v3 import E0V1E_v3


class E0V1E_v3_original_equity60(E0V1E_v3):
    tradable_balance_ratio = 0.97
    base_fraction = 0.60
    reserve_step = 0.133333
    _peak_balance = None

    def bot_start(self, **kwargs) -> None:
        self._peak_balance = None

    @classmethod
    def fraction_for_drawdown(cls, drawdown: float) -> float:
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
        original_stake = super().custom_stake_amount(
            pair=pair,
            current_time=current_time,
            current_rate=current_rate,
            proposed_stake=proposed_stake,
            min_stake=min_stake,
            max_stake=max_stake,
            leverage=leverage,
            entry_tag=entry_tag,
            side=side,
            **kwargs,
        )

        current_balance = self.wallets.get_total_stake_amount() if self.wallets else None
        if current_balance is None:
            target_fraction = self.base_fraction
        else:
            if self._peak_balance is None or current_balance > self._peak_balance:
                self._peak_balance = current_balance
            drawdown = max(0.0, 1.0 - current_balance / self._peak_balance)
            target_fraction = self.fraction_for_drawdown(drawdown)

        reserve_cap = proposed_stake * (target_fraction / self.tradable_balance_ratio)
        stake = min(original_stake, reserve_cap, max_stake)
        if min_stake is not None:
            stake = max(stake, min_stake)
        return stake
