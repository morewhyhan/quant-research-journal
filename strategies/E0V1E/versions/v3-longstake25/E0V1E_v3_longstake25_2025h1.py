from datetime import datetime, timedelta
import talib.abstract as ta
import pandas_ta as pta
from freqtrade.persistence import Trade
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import DecimalParameter, IntParameter, stoploss_from_absolute, timeframe_to_prev_date
from pandas import DataFrame
from functools import reduce
import warnings

warnings.simplefilter(action="ignore", category=RuntimeWarning)
TMP_HOLD = []
TMP_HOLD1 = []
TMP_HOLD_MAX_PROFIT = {}
ATR_STOP_CACHE = {}
# Short tracking
S_TMP_HOLD = []
S_TMP_HOLD_MAX_PROFIT = {}


class E0V1E_v3_longstake25_2025h1(IStrategy):
    minimal_roi = {"0": 1}
    timeframe = "5m"
    process_only_new_candles = True
    startup_candle_count = 240
    can_short = True
    order_types = {
        "entry": "market",
        "exit": "market",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_market_ratio": 0.99,
    }

    # === HarmonicDivergence 借鉴: trailing + ATR ===
    minimal_roi = {"0": 1}

    stoploss = -0.25
    trailing_stop = False
    trailing_stop_positive = 0.002
    trailing_stop_positive_offset = 0.05
    trailing_only_offset_is_reached = True

    use_custom_stoploss = True
    atr_stop_multiplier = 3.5
    atr_stop_floor = 0.12
    atr_stop_ceiling_long = 0.18

    # === Long entry params (unchanged) ===
    is_optimize_32 = True
    buy_rsi_fast_32 = IntParameter(20, 70, default=40, space="buy", optimize=is_optimize_32)
    buy_rsi_32 = IntParameter(15, 50, default=42, space="buy", optimize=is_optimize_32)
    buy_sma15_32 = DecimalParameter(0.900, 1, default=0.973, decimals=3, space="buy", optimize=is_optimize_32)
    buy_cti_32 = DecimalParameter(-1, 1, default=0.69, decimals=2, space="buy", optimize=is_optimize_32)

    sell_fastx = IntParameter(50, 100, default=84, space="sell", optimize=True)

    cci_opt = False
    sell_loss_cci = IntParameter(low=0, high=600, default=120, space="sell", optimize=cci_opt)
    sell_loss_cci_profit = DecimalParameter(-0.15, 0, default=-0.05, decimals=2, space="sell", optimize=cci_opt)
    buy_rsi_period = IntParameter(10, 190, default=20, space="buy")
    buy_rsi_fast_period = IntParameter(10, 190, default=10, space="buy")
    buy_rsi_slow_period = IntParameter(10, 190, default=40, space="buy")
    buy_sma_period = IntParameter(10, 190, default=15, space="buy")

    # === Short entry params (mirror of long, inverted) ===
    short_rsi_fast_32 = IntParameter(30, 80, default=60, space="sell", optimize=is_optimize_32)
    short_rsi_32 = IntParameter(50, 85, default=58, space="sell", optimize=is_optimize_32)
    short_sma15_32 = DecimalParameter(1.000, 1.100, default=1.027, decimals=3, space="sell", optimize=is_optimize_32)
    short_cti_32 = DecimalParameter(-1, 1, default=0.31, decimals=2, space="sell", optimize=is_optimize_32)

    short_fastk = IntParameter(0, 50, default=16, space="sell", optimize=True)
    short_cci = IntParameter(0, 600, default=480, space="sell", optimize=cci_opt)
    short_cci_profit = DecimalParameter(-0.15, 0, default=-0.05, decimals=2, space="sell", optimize=cci_opt)

    @property
    def protections(self):
        return [{"method": "CooldownPeriod", "stop_duration_candles": 18}]

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
        if side == "long":
            return proposed_stake * 0.25
        return proposed_stake

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # Short: stepped protection
        if trade.is_short:
            if current_profit >= 0.10:
                return -0.04
            if current_profit >= 0.05:
                return -0.02
            if current_profit >= 0.03:
                return -0.002
            return -0.15

        # Long: original profit protection first
        if current_profit >= 0.05:
            return -0.002
        if str(trade.enter_tag) == "buy_new" and current_profit >= 0.03:
            return -0.003
        if str(trade.enter_tag) != "buy_1":
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma_15"] = ta.SMA(dataframe, timeperiod=int(self.buy_sma_period.value))
        dataframe["cti"] = pta.cti(dataframe["close"], length=20)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=int(self.buy_rsi_period.value))
        dataframe["rsi_fast"] = ta.RSI(dataframe, timeperiod=int(self.buy_rsi_fast_period.value))
        dataframe["rsi_slow"] = ta.RSI(dataframe, timeperiod=int(self.buy_rsi_slow_period.value))
        stoch_fast = ta.STOCHF(dataframe, 5, 3, 0, 3, 0)
        dataframe["fastk"] = stoch_fast["fastk"]
        dataframe["cci"] = ta.CCI(dataframe, timeperiod=20)
        dataframe["ma120"] = ta.MA(dataframe, timeperiod=120)
        dataframe["ma240"] = ta.MA(dataframe, timeperiod=240)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions_long = []
        conditions_short = []
        dataframe.loc[:, "enter_tag"] = ""

        # === Long: buy_1 only in uptrend, buy_new always ===
        uptrend = dataframe["close"] > dataframe["ma240"]

        buy_1 = (
            (dataframe["rsi_slow"] < dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] < self.buy_rsi_fast_32.value)
            & (dataframe["rsi"] > self.buy_rsi_32.value)
            & (dataframe["close"] < dataframe["sma_15"] * self.buy_sma15_32.value)
            & (dataframe["cti"] < self.buy_cti_32.value)
            & uptrend  # only in uptrend
        )
        buy_new = (
            (dataframe["rsi_slow"] < dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] < 34)
            & (dataframe["rsi"] > 28)
            & (dataframe["close"] < dataframe["sma_15"] * 0.96)
            & (dataframe["cti"] < self.buy_cti_32.value)
        )
        conditions_long.append(buy_1)
        dataframe.loc[buy_1, "enter_tag"] += "buy_1"
        conditions_long.append(buy_new)
        dataframe.loc[buy_new, "enter_tag"] += "buy_new"

        # === Short: mirror of long ===
        downtrend = dataframe["close"] < dataframe["ma240"]

        short_1 = (
            (dataframe["rsi_slow"] > dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] > self.short_rsi_fast_32.value)
            & (dataframe["rsi"] < self.short_rsi_32.value)
            & (dataframe["close"] > dataframe["sma_15"] * self.short_sma15_32.value)
            & (dataframe["cti"] > self.short_cti_32.value)
            & (dataframe["close"] < dataframe["ma120"])
            & downtrend  # only in downtrend
        )
        short_new = (
            (dataframe["rsi_slow"] > dataframe["rsi_slow"].shift(1))
            & (dataframe["rsi_fast"] > 66)
            & (dataframe["rsi"] < 72)
            & (dataframe["close"] > dataframe["sma_15"] * 1.04)
            & (dataframe["cti"] > self.short_cti_32.value)
        )
        conditions_short.append(short_1)
        dataframe.loc[short_1, "enter_tag"] += "short_1"
        conditions_short.append(short_new)
        dataframe.loc[short_new, "enter_tag"] += "short_new"

        if conditions_long:
            dataframe.loc[reduce(lambda x, y: x | y, conditions_long), "enter_long"] = 1
        if conditions_short:
            dataframe.loc[reduce(lambda x, y: x | y, conditions_short), "enter_short"] = 1
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        current_candle = dataframe.iloc[-1].squeeze()
        min_profit = trade.calc_profit_ratio(trade.min_rate)
        is_short = trade.is_short

        # === Time gate: release from TMP_HOLD after 2h if not earning ===
        trade_duration_min = (current_time - trade.open_date_utc).total_seconds() / 60
        if trade_duration_min > 90 and current_profit < 0.03:
            if trade.id in TMP_HOLD:
                TMP_HOLD.remove(trade.id)
                del TMP_HOLD_MAX_PROFIT[trade.id]
            if trade.id in S_TMP_HOLD:
                S_TMP_HOLD.remove(trade.id)
                del S_TMP_HOLD_MAX_PROFIT[trade.id]
            if trade.id in TMP_HOLD1:
                TMP_HOLD1.remove(trade.id)

        # === MA120/MA240 trend hold logic ===
        if not is_short:
            # Long: price above both MAs + profit>1% → hold for trend
            if current_candle["close"] > current_candle["ma120"] and current_candle["close"] > current_candle["ma240"]:
                if current_profit > -0.01:  # allow hold entry when not losing
                    if trade.id not in TMP_HOLD:
                        TMP_HOLD.append(trade.id)
                        TMP_HOLD_MAX_PROFIT[trade.id] = current_profit
                    elif current_profit > TMP_HOLD_MAX_PROFIT.get(trade.id, 0):
                        TMP_HOLD_MAX_PROFIT[trade.id] = current_profit

            if (trade.open_rate - current_candle["ma120"]) / trade.open_rate >= 0.1:
                if trade.id not in TMP_HOLD1:
                    TMP_HOLD1.append(trade.id)
        # S_TMP_HOLD disabled - shorts exit via normal channels

        # === Fastk profit sell (long) / Fastk profit cover (short) ===
        if current_profit > 0:
            if not is_short and current_candle["fastk"] > self.sell_fastx.value:
                return "fastk_profit_sell"
            if is_short and current_candle["fastk"] < self.short_fastk.value:
                return "fastk_profit_cover"

        # === CCI loss sell/cover ===
        if min_profit <= -0.1:
            if current_profit > self.sell_loss_cci_profit.value:
                if not is_short and current_candle["cci"] > self.sell_loss_cci.value:
                    return "cci_loss_sell"
                if is_short and current_candle["cci"] < self.short_cci.value:
                    return "cci_loss_cover"

        # === MA120 hold exit logic ===
        if not is_short:
            if trade.id in TMP_HOLD1 and current_candle["close"] < current_candle["ma120"]:
                TMP_HOLD1.remove(trade.id)
                return "ma120_sell_fast"

            if trade.id in TMP_HOLD:
                max_profit = TMP_HOLD_MAX_PROFIT.get(trade.id, 0)
                if max_profit > 0.015 and current_profit < max_profit / 3:
                    TMP_HOLD.remove(trade.id)
                    del TMP_HOLD_MAX_PROFIT[trade.id]
                    return "ma120_profit_protect"

            if trade.id in TMP_HOLD and current_candle["close"] < current_candle["ma120"] and current_candle["close"] < current_candle["ma240"]:
                TMP_HOLD.remove(trade.id)
                del TMP_HOLD_MAX_PROFIT[trade.id]
                return "ma120_sell"
        # S_TMP_HOLD exits disabled - shorts use fastk/cci/stop only

        return None

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, ["exit_long", "exit_tag"]] = (0, "long_out")
        dataframe.loc[:, ["exit_short", "exit_tag"]] = (0, "short_out")
        return dataframe
