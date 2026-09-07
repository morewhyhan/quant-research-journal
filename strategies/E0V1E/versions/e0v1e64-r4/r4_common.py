"""R4-only causal features and guards; no edits to the frozen V5 parents."""
import math

import pandas as pd


def closed_bar_time(current_time):
    """OHLCV dates denote opens: the last completed 5m bar opened here."""
    return pd.Timestamp(current_time).floor("5min") - pd.Timedelta(minutes=5)


class R4ResearchMixin:
    """These initial hypotheses are deliberately disabled outside backtesting."""
    max_open_trades = 1

    def bot_start(self, **kwargs):
        mode = self.config.get("runmode")
        if getattr(mode, "value", mode) != "backtest":
            raise RuntimeError("V14-V17 are backtest-only research, not live/dry-run strategies.")
        if self.config.get("max_open_trades", self.max_open_trades) != 1:
            raise RuntimeError("R4 requires one shared-capital slot; do not override it.")
        super().bot_start(**kwargs)

    def populate_indicators(self, dataframe, metadata):
        frame = super().populate_indicators(dataframe, metadata)
        frame["r4_return_4h"] = frame["close"].pct_change(48, fill_method=None)
        # Base-volume * close is a liquidity proxy, not exact executed quote volume.
        frame["r4_quote_volume_1h"] = (frame["close"] * frame["volume"]).rolling(12).sum()
        frame["r4_ma_2h"] = frame["close"].rolling(24).mean()
        frame["r4_ma_2h_old"] = frame["r4_ma_2h"].shift(12)
        frame["r4_trend_long"] = ((frame["close"] > frame["ma240"])
                                   & (frame["ma120"] > frame["ma120"].shift(12)))
        frame["r4_trend_short"] = ((frame["close"] < frame["ma240"])
                                    & (frame["ma120"] < frame["ma120"].shift(12)))
        return frame

    def r4_completed_frame(self, pair, current_time):
        frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if frame.empty:
            return frame
        cutoff = closed_bar_time(current_time)
        frame = frame.loc[frame["date"] <= cutoff]
        if frame.empty or pd.Timestamp(frame.iloc[-1]["date"]) != cutoff:
            return frame.iloc[:0]  # Stale bars must not qualify new R4 decisions.
        return frame

    @staticmethod
    def strong_trend(frame, side):
        """V5 trend plus positive directional 4h momentum and a rising/falling 2h MA."""
        if frame.empty or side not in ("long", "short"):
            return False
        row = frame.iloc[-1]
        required = ("close", "ma120", "ma240", "r4_ma_2h", "r4_ma_2h_old", "r4_return_4h")
        if any(not math.isfinite(float(row.get(key, float("nan")))) for key in required):
            return False
        direction = 1 if side == "long" else -1
        return bool(row.get("r4_trend_" + side, False)
                    and direction * (row["close"] - row["ma120"]) > 0
                    and direction * (row["r4_ma_2h"] - row["r4_ma_2h_old"]) > 0
                    and direction * row["r4_return_4h"] > 0)
