"""V13: three shared-capital slots, at most two open trades in the same direction."""
from freqtrade.persistence import Trade
from E0V1E64_V5 import E0V1E64_V5


class E0V1E64_V13(E0V1E64_V5):
    max_open_trades = 3

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        opened = [t for t in Trade.get_trades_proxy(is_open=True)
                  if t.open_date_utc <= current_time]
        if sum(bool(t.is_short) == (side == "short") for t in opened) >= 2:
            return False
        return super().confirm_trade_entry(pair, order_type, amount, rate, time_in_force,
                                           current_time, entry_tag, side, **kwargs)
