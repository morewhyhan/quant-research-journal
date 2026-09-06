"""Shared helpers; frozen server signal/exit implementation is unchanged."""
from datetime import timedelta
import math
from E0V1E_v3_equity60_reserve40 import E0V1E_v3_equity60_reserve40


class ResearchBase(E0V1E_v3_equity60_reserve40):
    def bot_start(self, **kwargs):
        mode = self.config.get("runmode")
        if getattr(mode, "value", mode) == "live":
            raise RuntimeError("E0V1E64 is local research, not approved for live deployment.")
        super().bot_start(**kwargs)

    def completed_frame(self, pair, current_time):
        frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if frame.empty:
            return frame
        cutoff = current_time - timedelta(minutes=5)
        if frame.iloc[-1]["date"] > cutoff:
            frame = frame.loc[frame["date"] <= cutoff]
        return frame

    @staticmethod
    def favorable_trend(frame, side):
        if len(frame) < 13:
            return False
        latest, old = frame.iloc[-1], frame.iloc[-13]
        if side == "short":
            return bool(latest["close"] < latest["ma240"]
                        and latest["ma120"] < old["ma120"])
        return bool(latest["close"] > latest["ma240"]
                    and latest["ma120"] > old["ma120"])

    @staticmethod
    def bound_stake(stake, min_stake, max_stake):
        if not math.isfinite(stake):
            return 0.0
        return min(max(stake, min_stake or 0.0), max_stake)
