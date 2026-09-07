"""V11: recent closed-trade regime budget replaces the drawdown-add ladder."""
import math
from freqtrade.persistence import Trade
from E0V1E64_V5 import E0V1E64_V5


class E0V1E64_V11(E0V1E64_V5):
    @staticmethod
    def budget_fraction(ratios, drawdown):
        # No trade-by-trade re-fitting: thresholds frozen before the test.
        target = 0.60
        if len(ratios) >= 30:
            recent = ratios[-30:]
            gain = sum(max(r, 0.0) for r in recent)
            loss = -sum(min(r, 0.0) for r in recent)
            mean = sum(recent) / len(recent)
            pf = gain / loss if loss else (float("inf") if gain else 0.0)
            if mean <= 0 or pf < 1.0:
                target = 0.40
            elif pf >= 1.5:
                target = 0.90
        if drawdown >= 0.20:
            target = min(target, 0.40)
        elif drawdown >= 0.10:
            target = min(target, 0.60)
        return target

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        if self.wallets is None:
            return proposed_stake * 0.60 / self.tradable_balance_ratio
        equity = self.wallets.get_total_stake_amount()
        peak = max(equity, self._peak_tradable_balance or equity)
        self._peak_tradable_balance = peak
        drawdown = max(0.0, 1.0 - equity / peak) if peak > 0 else 0.0
        closed = [t for t in Trade.get_trades_proxy(is_open=False)
                  if t.close_date_utc is not None and t.close_date_utc <= current_time
                  and t.close_profit is not None and math.isfinite(t.close_profit)]
        closed.sort(key=lambda t: (t.close_date_utc, t.id))
        target = self.budget_fraction([float(t.close_profit) for t in closed[-30:]], drawdown)
        stake = proposed_stake * target / self.tradable_balance_ratio
        cap = min(proposed_stake, max_stake)
        if (min_stake or 0) > cap:
            return 0.0
        return self.bound_stake(stake, min_stake, cap)
