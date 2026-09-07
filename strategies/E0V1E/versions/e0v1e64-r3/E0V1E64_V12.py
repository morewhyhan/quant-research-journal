"""V12: long-only entry-relative catastrophe stop; preserve V5 short/profit rules."""
from freqtrade.strategy import stoploss_from_absolute
from E0V1E64_V5 import E0V1E64_V5


class E0V1E64_V12(E0V1E64_V5):
    long_max_price_loss = 0.15

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        original = super().custom_stoploss(pair, trade, current_time, current_rate, current_profit, **kwargs)
        if trade.is_short:
            return original
        stop_rate = trade.open_rate * (1.0 - self.long_max_price_loss)
        distance = stoploss_from_absolute(stop_rate, current_rate,
                                          is_short=False, leverage=trade.leverage)
        # The tighter of the original profit protector and the fixed entry floor.
        # This is an intended price threshold, not a loss guarantee under gaps/fees.
        return min(abs(original), distance) if original is not None else distance
