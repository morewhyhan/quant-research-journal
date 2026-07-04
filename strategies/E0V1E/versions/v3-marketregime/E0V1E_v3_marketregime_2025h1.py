from functools import reduce

from pandas import DataFrame
from freqtrade.strategy import stoploss_from_absolute, timeframe_to_prev_date

from E0V1E_v3_longstake25_2025h1 import ATR_STOP_CACHE, E0V1E_v3_longstake25_2025h1


class E0V1E_v3_marketregime_2025h1(E0V1E_v3_longstake25_2025h1):
    """
    E0V1E longstake25 with a BTC/ETH market-regime gate.

    The base entries and exits are preserved.  This variant only changes:
    - broad-market bull/bear/neutral detection from BTC and ETH 5m data,
    - entry gating so bull regimes favor longs and bear regimes favor shorts,
    - stake sizing so the favored direction receives full stake.
    """

    def informative_pairs(self):
        return [("BTC/USDT:USDT", self.timeframe), ("ETH/USDT:USDT", self.timeframe)]

    @staticmethod
    def _base_tag(tag) -> str:
        tag = str(tag or "")
        for prefix in ("buy_1", "buy_new", "short_1", "short_new"):
            if tag.startswith(prefix):
                return prefix
        return tag

    @staticmethod
    def _append_regime_tag(dataframe: DataFrame, mask, tag: str) -> None:
        dataframe.loc[mask & dataframe["market_bull"], "enter_tag"] += f"{tag}_bull"
        dataframe.loc[mask & dataframe["market_bear"], "enter_tag"] += f"{tag}_bear"
        dataframe.loc[mask & dataframe["market_neutral"], "enter_tag"] += f"{tag}_neutral"

    @staticmethod
    def _market_features(market: DataFrame, prefix: str) -> DataFrame:
        market = market[["date", "close"]].copy()
        market[f"{prefix}_ret_4h"] = market["close"] / market["close"].shift(48) - 1
        market[f"{prefix}_ret_1d"] = market["close"] / market["close"].shift(288) - 1
        market[f"{prefix}_ret_7d"] = market["close"] / market["close"].shift(2016) - 1
        market[f"{prefix}_ema_2d"] = market["close"].ewm(span=576, min_periods=48).mean()
        market[f"{prefix}_ema_7d"] = market["close"].ewm(span=2016, min_periods=288).mean()
        market = market.rename(columns={"close": f"{prefix}_close"})
        return market[
            [
                "date",
                f"{prefix}_close",
                f"{prefix}_ret_4h",
                f"{prefix}_ret_1d",
                f"{prefix}_ret_7d",
                f"{prefix}_ema_2d",
                f"{prefix}_ema_7d",
            ]
        ]

    def _merge_market_pair(self, dataframe: DataFrame, pair: str, prefix: str) -> DataFrame:
        if not self.dp:
            return dataframe

        market = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        if market is None or market.empty:
            return dataframe

        market = self._market_features(market, prefix)
        dataframe = dataframe.drop(columns=[c for c in market.columns if c != "date"], errors="ignore")
        dataframe = dataframe.merge(market, on="date", how="left")
        market_cols = [c for c in market.columns if c != "date"]
        dataframe[market_cols] = dataframe[market_cols].ffill()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe = self._merge_market_pair(dataframe, "BTC/USDT:USDT", "btc")
        dataframe = self._merge_market_pair(dataframe, "ETH/USDT:USDT", "eth")

        required = [
            "btc_close",
            "btc_ret_4h",
            "btc_ret_1d",
            "btc_ret_7d",
            "btc_ema_2d",
            "btc_ema_7d",
            "eth_close",
            "eth_ret_4h",
            "eth_ret_1d",
            "eth_ret_7d",
            "eth_ema_2d",
            "eth_ema_7d",
        ]
        for col in required:
            if col not in dataframe:
                dataframe[col] = 0.0

        btc_above = dataframe["btc_close"] > dataframe["btc_ema_7d"]
        btc_fast_above = dataframe["btc_ema_2d"] > dataframe["btc_ema_7d"]
        eth_above = dataframe["eth_close"] > dataframe["eth_ema_7d"]
        eth_fast_above = dataframe["eth_ema_2d"] > dataframe["eth_ema_7d"]

        bull_score = (
            btc_above.astype(int) * 2
            + btc_fast_above.astype(int)
            + (dataframe["btc_ret_7d"] > 0).astype(int)
            + eth_above.astype(int)
            + eth_fast_above.astype(int)
            + (dataframe["eth_ret_7d"] > 0).astype(int)
        )
        bear_score = (
            (~btc_above).astype(int) * 2
            + (~btc_fast_above).astype(int)
            + (dataframe["btc_ret_7d"] < 0).astype(int)
            + (~eth_above).astype(int)
            + (~eth_fast_above).astype(int)
            + (dataframe["eth_ret_7d"] < 0).astype(int)
        )

        dataframe["market_bull"] = bull_score >= 4
        dataframe["market_bear"] = bear_score >= 4
        dataframe["market_neutral"] = ~(dataframe["market_bull"] | dataframe["market_bear"])
        dataframe["market_regime"] = 0
        dataframe.loc[dataframe["market_bull"], "market_regime"] = 1
        dataframe.loc[dataframe["market_bear"], "market_regime"] = -1
        return dataframe

    def custom_stake_amount(
        self,
        pair,
        current_time,
        current_rate,
        proposed_stake,
        min_stake,
        max_stake,
        leverage,
        entry_tag,
        side,
        **kwargs,
    ):
        tag = str(entry_tag or "")
        if "_bull" in tag:
            regime = 1
        elif "_bear" in tag:
            regime = -1
        else:
            regime = 0

        if side == "long":
            if regime == 1:
                return proposed_stake
            if regime == -1:
                return proposed_stake * 0.20
            return proposed_stake * 0.45

        if regime == -1:
            return proposed_stake
        if regime == 1:
            return proposed_stake * 0.20
        return proposed_stake * 0.45

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if trade.is_short:
            if current_profit >= 0.10:
                return -0.04
            if current_profit >= 0.05:
                return -0.02
            if current_profit >= 0.03:
                return -0.002
            return -0.15

        base_tag = self._base_tag(trade.enter_tag)
        if current_profit >= 0.05:
            return -0.002
        if base_tag == "buy_new" and current_profit >= 0.03:
            return -0.003
        if base_tag != "buy_1":
            return None

        atr_stop_rate = ATR_STOP_CACHE.get(trade.id)
        if atr_stop_rate is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            trade_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
            trade_candle = dataframe.loc[dataframe["date"] == trade_date]

            if not trade_candle.empty:
                candle = trade_candle.squeeze()
                atr = candle.get("atr")

                if atr and atr == atr:
                    atr_stop_rate = candle["low"] - (atr * self.atr_stop_multiplier)
                    ATR_STOP_CACHE[trade.id] = atr_stop_rate

        atr_stop = None
        if atr_stop_rate is not None:
            atr_stop = stoploss_from_absolute(
                atr_stop_rate,
                current_rate,
                is_short=False,
                leverage=trade.leverage,
            )
            atr_stop = min(max(atr_stop, self.atr_stop_floor), self.atr_stop_ceiling_long)
        return atr_stop

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions_long = []
        conditions_short = []
        dataframe.loc[:, "enter_tag"] = ""

        uptrend = dataframe["close"] > dataframe["ma240"]
        downtrend = dataframe["close"] < dataframe["ma240"]

        long_regime_ok = dataframe["market_bull"] | (
            dataframe["market_neutral"] & (dataframe["btc_ret_4h"] >= -0.003)
        )
        short_regime_ok = dataframe["market_bear"] | (
            dataframe["market_neutral"] & (dataframe["btc_ret_4h"] <= 0.003)
        )

        buy_1 = (
            (dataframe["rsi_slow"] < dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] < self.buy_rsi_fast_32.value)
            & (dataframe["rsi"] > self.buy_rsi_32.value)
            & (dataframe["close"] < dataframe["sma_15"] * self.buy_sma15_32.value)
            & (dataframe["cti"] < self.buy_cti_32.value)
            & uptrend
            & long_regime_ok
        )
        buy_new = (
            (dataframe["rsi_slow"] < dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] < 34)
            & (dataframe["rsi"] > 28)
            & (dataframe["close"] < dataframe["sma_15"] * 0.96)
            & (dataframe["cti"] < self.buy_cti_32.value)
            & long_regime_ok
        )
        conditions_long.append(buy_1)
        self._append_regime_tag(dataframe, buy_1, "buy_1")
        conditions_long.append(buy_new)
        self._append_regime_tag(dataframe, buy_new, "buy_new")

        short_1 = (
            (dataframe["rsi_slow"] > dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] > self.short_rsi_fast_32.value)
            & (dataframe["rsi"] < self.short_rsi_32.value)
            & (dataframe["close"] > dataframe["sma_15"] * self.short_sma15_32.value)
            & (dataframe["cti"] > self.short_cti_32.value)
            & (dataframe["close"] < dataframe["ma120"])
            & downtrend
            & short_regime_ok
        )
        short_new = (
            (dataframe["rsi_slow"] > dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] > 66)
            & (dataframe["rsi"] < 72)
            & (dataframe["close"] > dataframe["sma_15"] * 1.04)
            & (dataframe["cti"] > self.short_cti_32.value)
            & short_regime_ok
        )
        conditions_short.append(short_1)
        self._append_regime_tag(dataframe, short_1, "short_1")
        conditions_short.append(short_new)
        self._append_regime_tag(dataframe, short_new, "short_new")

        if conditions_long:
            dataframe.loc[reduce(lambda x, y: x | y, conditions_long), "enter_long"] = 1
        if conditions_short:
            dataframe.loc[reduce(lambda x, y: x | y, conditions_short), "enter_short"] = 1
        return dataframe
