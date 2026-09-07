"""Offline contract/regression tests; no exchange, historical backtest, or orders."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "my-strategies/E0V1E64_R4"
sys.path.insert(0, str(SOURCE))
from E0V1E64_V5 import E0V1E64_V5
from E0V1E64_V14 import E0V1E64_V14
from E0V1E64_V15 import E0V1E64_V15
from E0V1E64_V16 import E0V1E64_V16
from E0V1E64_V17 import E0V1E64_V17
from research_common import ResearchBase
from r4_common import closed_bar_time

NOW = datetime(2026, 4, 1, 12, tzinfo=timezone.utc)
VARIANTS = (E0V1E64_V14, E0V1E64_V15, E0V1E64_V16, E0V1E64_V17)


def strong_frame(side="long", count=30):
    short = side == "short"
    return pd.DataFrame({
        "date": pd.date_range(end=NOW-timedelta(minutes=5), periods=count, freq="5min"),
        "close": 80.0 if short else 120.0,
        "ma120": np.linspace(115, 110, count) if short else np.linspace(105, 110, count),
        "ma240": 100.0,
        "r4_ma_2h": 90.0 if short else 115.0,
        "r4_ma_2h_old": 92.0 if short else 112.0,
        "r4_return_4h": -.04 if short else .04,
        "r4_quote_volume_1h": 1000.0,
        "r4_trend_long": not short, "r4_trend_short": short,
        "enter_long": int(not short), "enter_short": int(short),
        "exit_long": 0, "exit_short": 0,
    })


def strategy(cls, frame=None, pairs=("A", "B")):
    s = cls({"runmode": "backtest", "max_open_trades": 1})
    s.dp = SimpleNamespace(get_analyzed_dataframe=lambda *a, **k: (frame, None),
                           current_whitelist=lambda: list(pairs))
    s.wallets = SimpleNamespace(get_total_stake_amount=lambda: 970.0)
    s._peak_tradable_balance = 970.0
    s.is_pair_locked = lambda *a, **k: False
    return s


def trade(short=False, age=180):
    state = {}
    return SimpleNamespace(
        id=9001, is_short=short, open_date_utc=NOW-timedelta(minutes=age),
        open_rate=100.0, leverage=1.0, enter_tag="short_1" if short else "buy_1",
        get_custom_data=lambda key, default=None: state.get(key, default),
        set_custom_data=lambda key, value: state.__setitem__(key, value), state=state,
    )


def confirm(s, pair, side="long", when=NOW):
    return s.confirm_trade_entry(pair, "market", 1, 100, "GTC", when, "test", side)


def stake(s, side="long", when=NOW, minimum=1, available=970):
    return s.custom_stake_amount("A", when, 100, 970, minimum, available, 1, "test", side)


class Contracts(unittest.TestCase):
    def test_frozen_parents_byte_identical(self):
        for name in ("E0V1E_v3.py", "E0V1E_v3_equity60_reserve40.py",
                     "E0V1E_v3_equity60_reserve40.json", "research_common.py",
                     "E0V1E64_V5.py", "E0V1E64_V5.json"):
            self.assertEqual((SOURCE/name).read_bytes(),
                             (ROOT/"my-strategies/E0V1E64_R3"/name).read_bytes(), name)

    def test_real_resolver_and_exact_v5_parameters(self):
        from freqtrade.resolvers import StrategyResolver
        expected = json.loads((SOURCE/"E0V1E64_V5.json").read_text())["params"]
        for cls in VARIANTS:
            payload = json.loads((SOURCE/(cls.__name__+".json")).read_text())
            self.assertEqual(payload["strategy_name"], cls.__name__)
            self.assertEqual(payload["params"], expected)
            cfg = {"strategy": cls.__name__, "strategy_path": str(SOURCE),
                   "user_data_dir": ROOT/"user_data", "stake_currency": "USDT",
                   "stake_amount": "unlimited", "max_open_trades": 1,
                   "trading_mode": "futures", "runmode": "backtest"}
            s = StrategyResolver.load_strategy(cfg)
            s.ft_load_hyper_params(False)
            s.bot_start()
            for section in ("buy", "sell"):
                for key, value in expected[section].items():
                    self.assertAlmostEqual(getattr(s, key).value, value)
            self.assertEqual(s.stoploss, -.25)
            self.assertEqual(s.max_extension_minutes, 60)
            self.assertEqual(s.max_open_trades, 1)
            self.assertIn(E0V1E64_V5, cls.__bases__)

    def test_research_guards_and_slot_override(self):
        for cls in VARIANTS:
            for mode in ("live", "dry_run", "hyperopt", None):
                with self.assertRaises(RuntimeError):
                    cls({"runmode": mode}).bot_start()
            with self.assertRaises(RuntimeError):
                cls({"runmode": "backtest", "max_open_trades": 3}).bot_start()

    def test_original_indicators_and_signals_preserved(self):
        x = np.arange(340)
        close = 100 + x*.01 + np.sin(x*.17)*8
        raw = pd.DataFrame({"date": pd.date_range("2026-03-01", periods=len(x), freq="5min", tz="UTC"),
                            "open": close+.1, "close": close, "high": close+1,
                            "low": close-1, "volume": 100.0+x})
        base = E0V1E64_V5({})
        expected = base.populate_indicators(raw.copy(), {"pair": "A"})
        expected = base.ft_advise_signals(expected, {"pair": "A"})
        for cls in VARIANTS:
            s = strategy(cls)
            actual = s.populate_indicators(raw.copy(), {"pair": "A"})
            actual = s.ft_advise_signals(actual, {"pair": "A"})
            pd.testing.assert_frame_equal(expected, actual[expected.columns])
            prefix = s.populate_indicators(raw.iloc[:310].copy(), {"pair": "A"})
            pd.testing.assert_frame_equal(actual.iloc[:310][prefix.columns], prefix)
            if cls is E0V1E64_V14:
                self.assertIn("A", s._rank_frames)

    def test_current_and_stale_candles_cannot_qualify(self):
        self.assertEqual(closed_bar_time(NOW+timedelta(minutes=2)), pd.Timestamp(NOW)-pd.Timedelta(minutes=5))
        for cls in VARIANTS:
            frame = strong_frame()
            future = frame.iloc[[-1]].copy()
            future["date"] = NOW
            future["close"] = 1e9
            s = strategy(cls, pd.concat([frame, future], ignore_index=True))
            self.assertEqual(len(s.r4_completed_frame("A", NOW)), len(frame))
            s = strategy(cls, frame.iloc[:-1])
            self.assertTrue(s.r4_completed_frame("A", NOW).empty)

    def test_original_stoploss_not_loosened(self):
        original = strategy(E0V1E64_V5)
        for cls in VARIANTS:
            s = strategy(cls)
            for short in (False, True):
                t = trade(short)
                for profit in (-.12, .02, .03, .05, .10):
                    self.assertEqual(s.custom_stoploss("A", t, NOW, 100, profit),
                                     original.custom_stoploss("A", t, NOW, 100, profit))


class RankingTests(unittest.TestCase):
    def test_real_engine_signal_shift_and_startup_alignment(self):
        from freqtrade.optimize.backtesting import Backtesting, DATE_IDX
        from freqtrade.configuration import TimeRange
        s = strategy(E0V1E64_V14)
        frames = {}
        for pair in ("A", "B"):
            frame = strong_frame(count=260)
            frame["open"], frame["high"], frame["low"] = 120., 121., 119.
            frame["volume"] = 100.
            if pair == "B":
                frame["r4_quote_volume_1h"] = 10000.
            frames[pair] = frame
        # Use the actual engine's conversion/shift path with an in-memory provider.
        # Only entry generation is stubbed to prescribe simultaneous signals.
        engine = Backtesting.__new__(Backtesting)
        engine.strategy, engine.timeframe = s, "5m"
        engine.required_startup, engine.timerange = 240, TimeRange()
        engine.config, engine.abort = {"candle_type_def": "futures"}, False
        engine.progress = SimpleNamespace(init_step=lambda *a: None, increment=lambda: None)
        engine.dataprovider = SimpleNamespace(_set_cached_df=lambda *a: None)
        with patch.object(E0V1E64_V5, "populate_entry_trend", side_effect=lambda frame, metadata: frame):
            converted = engine._get_ohlcv_as_lists(frames)
        first_signal_time = s._rank_frames["A"].index[0]
        first_entry_time = pd.Timestamp(converted["A"][0][DATE_IDX])
        self.assertEqual(first_entry_time, first_signal_time+pd.Timedelta(minutes=5))
        self.assertFalse(confirm(s, "B", when=first_signal_time.to_pydatetime()))
        self.assertFalse(confirm(s, "A", when=first_entry_time.to_pydatetime()))
        self.assertTrue(confirm(s, "B", when=first_entry_time.to_pydatetime()))
        # Insufficient startup data must not block another eligible candidate.
        s.populate_exit_trend(strong_frame(count=239), {"pair": "B"})
        self.assertTrue(confirm(s, "A", when=first_entry_time.to_pydatetime()))

    def prepared(self, reverse=False):
        s = strategy(E0V1E64_V14, pairs=("B", "A") if reverse else ("A", "B"))
        a, b = strong_frame(), strong_frame()
        a["r4_return_4h"], a["r4_quote_volume_1h"], a["r4_trend_long"] = .01, 100, False
        for pair, frame in (("B", b), ("A", a)) if reverse else (("A", a), ("B", b)):
            s._store_rank_frame(pair, frame)
        return s

    def test_best_signal_is_independent_of_pair_and_callback_order(self):
        for reverse in (False, True):
            s = self.prepared(reverse)
            self.assertFalse(confirm(s, "A"))
            self.assertTrue(confirm(s, "B"))
            self.assertFalse(confirm(s, "A"))
            self.assertAlmostEqual(s.ranked_signals(NOW)[0]["score"], 1)

    def test_future_suffix_cannot_change_current_winner(self):
        s = self.prepared()
        expected = s.ranked_signals(NOW)
        a = strong_frame()
        a["r4_return_4h"], a["r4_quote_volume_1h"], a["r4_trend_long"] = .01, 100, False
        future = a.iloc[[-1]].copy()
        future["date"], future["r4_return_4h"] = NOW, 1000
        future["r4_quote_volume_1h"], future["r4_trend_long"] = 1e20, True
        s._store_rank_frame("A", pd.concat([a, future], ignore_index=True))
        self.assertEqual(s.ranked_signals(NOW), expected)

    def test_ties_use_pair_name_and_cache_resets(self):
        s = strategy(E0V1E64_V14)
        for pair in ("B", "A"):
            s._store_rank_frame(pair, strong_frame())
        self.assertTrue(confirm(s, "A"))
        self.assertFalse(confirm(s, "B"))
        s.bot_start()
        self.assertFalse(confirm(s, "A"))

    def test_colliding_signals_and_exit_flags_excluded(self):
        for collision in ("enter_short", "exit_long"):
            s = self.prepared()
            b = strong_frame()
            b[collision] = 1
            s._store_rank_frame("B", b)
            self.assertFalse(confirm(s, "B"))
            self.assertTrue(confirm(s, "A"))

    def test_stale_invalid_and_outside_whitelist_excluded(self):
        for field, value in (("r4_return_4h", float("nan")), ("r4_quote_volume_1h", 0)):
            s = self.prepared()
            b = strong_frame()
            b[field] = value
            s._store_rank_frame("B", b)
            self.assertTrue(confirm(s, "A"))
        s = self.prepared()
        s._store_rank_frame("B", strong_frame().iloc[:-1])
        s._store_rank_frame("Z", strong_frame())
        self.assertTrue(confirm(s, "A"))
        self.assertFalse(confirm(s, "Z"))

    def test_locked_winner_is_skipped_and_errors_fail_closed(self):
        s = self.prepared()
        s.is_pair_locked = lambda pair, **kw: pair == "B"
        self.assertTrue(confirm(s, "A"))
        with patch.object(s, "ranked_signals", side_effect=ValueError("test error")):
            with self.assertLogs("E0V1E64_V14", level="ERROR"):
                self.assertFalse(confirm(s, "A"))

    def test_short_relative_strength_is_direction_correct(self):
        s = strategy(E0V1E64_V14)
        a, b = strong_frame("short"), strong_frame("short")
        a["r4_return_4h"], b["r4_return_4h"] = -.02, -.08
        s._store_rank_frame("A", a)
        s._store_rank_frame("B", b)
        self.assertTrue(confirm(s, "B", "short"))
        self.assertFalse(confirm(s, "A", "short"))


class ExtensionTests(unittest.TestCase):
    @patch.object(ResearchBase, "custom_exit", return_value="fastk_profit_sell")
    def test_new_eligibility_at_three_percent_and_existing_small_winner(self, mock):
        for profit in (.02, .03, .08):
            t = trade()
            s = strategy(E0V1E64_V15, strong_frame())
            self.assertIsNone(s.custom_exit("A", t, NOW, 108, profit))
            self.assertEqual(t.state["v5_extension"]["peak"], profit)

    @patch.object(ResearchBase, "custom_exit", return_value="fastk_profit_cover")
    def test_short_large_winner_and_weak_trend(self, mock):
        t = trade(True)
        s = strategy(E0V1E64_V15, strong_frame("short"))
        self.assertIsNone(s.custom_exit("A", t, NOW, 92, .08))
        weak = strong_frame("short")
        weak["r4_return_4h"] = .02
        s = strategy(E0V1E64_V15, weak)
        self.assertEqual(s.custom_exit("A", trade(True), NOW, 92, .08), "fastk_profit_cover")

    @patch.object(ResearchBase, "custom_exit", return_value="fastk_profit_sell")
    def test_peak_floor_and_timeout_not_restarted(self, mock):
        for elapsed, profit, expected in ((10, .039, "v5_profit_floor"),
                                          (60, .09, "v5_extension_timeout")):
            t = trade()
            t.set_custom_data("v5_extension", {"started": (NOW-timedelta(minutes=elapsed)).timestamp(), "peak": .08})
            s = strategy(E0V1E64_V15, strong_frame())
            self.assertEqual(s.custom_exit("A", t, NOW, 108, profit), expected)
            self.assertEqual(t.state["v5_extension"]["started"], (NOW-timedelta(minutes=elapsed)).timestamp())

    @patch.object(ResearchBase, "custom_exit", return_value="ma120_sell")
    def test_non_fastk_exit_keeps_priority(self, mock):
        self.assertEqual(strategy(E0V1E64_V15, strong_frame()).custom_exit("A", trade(), NOW, 108, .08), "ma120_sell")

    @patch.object(ResearchBase, "custom_exit", return_value="fastk_profit_sell")
    def test_future_strong_bar_does_not_extend_weak_completed_bar(self, mock):
        frame = strong_frame()
        frame["r4_return_4h"] = -.04
        future = strong_frame().iloc[[-1]].copy()
        future["date"] = NOW
        s = strategy(E0V1E64_V15, pd.concat([frame, future], ignore_index=True))
        self.assertEqual(s.custom_exit("A", trade(), NOW, 108, .08), "fastk_profit_sell")


class FailedReboundTests(unittest.TestCase):
    def failed(self, short=False):
        frame = strong_frame("short" if not short else "long")
        return frame

    @patch.object(E0V1E64_V5, "custom_exit", return_value=None)
    def test_long_and_short_failures(self, mock):
        for short in (False, True):
            s = strategy(E0V1E64_V16, self.failed(short))
            self.assertEqual(s.custom_exit("A", trade(short), NOW, 100, -.06),
                             "v16_failed_rebound_short" if short else "v16_failed_rebound_long")

    @patch.object(E0V1E64_V5, "custom_exit", return_value=None)
    def test_age_loss_and_recovery_conditions_are_all_required(self, mock):
        for age, profit in ((119, -.10), (180, -.059), (180, float("nan"))):
            s = strategy(E0V1E64_V16, self.failed())
            self.assertIsNone(s.custom_exit("A", trade(age=age), NOW, 100, profit))
        for col, value in (("close", 95), ("r4_ma_2h_old", 88)):
            frame = self.failed()
            frame.loc[frame.index[-2], col] = value
            s = strategy(E0V1E64_V16, frame)
            self.assertIsNone(s.custom_exit("A", trade(), NOW, 100, -.10))

    @patch.object(E0V1E64_V5, "custom_exit", return_value=None)
    def test_missing_stale_nan_and_short_history_do_not_trigger(self, mock):
        original = self.failed()
        nan_frame = original.copy()
        nan_frame.loc[nan_frame.index[-3], "r4_ma_2h"] = float("nan")
        for frame in (original.iloc[-11:], original.drop(original.index[-5]), original.iloc[:-1], nan_frame):
            self.assertIsNone(strategy(E0V1E64_V16, frame).custom_exit("A", trade(), NOW, 100, -.10))

    @patch.object(E0V1E64_V5, "custom_exit", return_value="original_exit")
    def test_parent_exit_priority(self, mock):
        self.assertEqual(strategy(E0V1E64_V16, self.failed()).custom_exit("A", trade(), NOW, 100, -.10), "original_exit")

    @patch.object(E0V1E64_V5, "custom_exit", return_value=None)
    def test_future_recovery_is_not_used(self, mock):
        frame = self.failed()
        future = strong_frame().iloc[[-1]].copy()
        future["date"] = NOW
        s = strategy(E0V1E64_V16, pd.concat([frame, future], ignore_index=True))
        self.assertEqual(s.custom_exit("A", trade(), NOW, 100, -.10), "v16_failed_rebound_long")


class ReserveTests(unittest.TestCase):
    def test_qualified_drawdown_uses_existing_ladder_not_extra_leverage(self):
        for side in ("long", "short"):
            for dd in (0, .06, .12, .22):
                s = strategy(E0V1E64_V17, strong_frame(side))
                s._peak_tradable_balance = 970/(1-dd)
                expected = 1000 * s.fraction_for_drawdown(dd)
                self.assertAlmostEqual(stake(s, side), expected)

    def test_weak_missing_or_conflicting_signal_keeps_sixty_percent(self):
        for col, value in (("r4_return_4h", -.04), ("enter_long", 0), ("enter_short", 1), ("exit_long", 1)):
            frame = strong_frame()
            frame[col] = value
            s = strategy(E0V1E64_V17, frame)
            s._peak_tradable_balance = 1400
            self.assertAlmostEqual(stake(s), 600)
        s = strategy(E0V1E64_V17, strong_frame().iloc[:-1])
        s._peak_tradable_balance = 1400
        self.assertAlmostEqual(stake(s), 600)

    def test_cash_minimum_and_invalid_wallet_bounds(self):
        s = strategy(E0V1E64_V17, strong_frame())
        s._peak_tradable_balance = 1400
        self.assertEqual(stake(s, available=400), 400)
        self.assertEqual(stake(s, available=400, minimum=500), 0)
        s.wallets = None
        self.assertAlmostEqual(stake(s), 600)
        s.wallets = SimpleNamespace(get_total_stake_amount=lambda: float("nan"))
        self.assertEqual(stake(s), 0)

    def test_highwater_updates_and_future_quality_does_not_release_reserve(self):
        frame = strong_frame()
        frame["r4_return_4h"] = -.04
        future = strong_frame().iloc[[-1]].copy()
        future["date"] = NOW
        s = strategy(E0V1E64_V17, pd.concat([frame, future], ignore_index=True))
        s._peak_tradable_balance = 1400
        self.assertAlmostEqual(stake(s), 600)
        s.wallets = SimpleNamespace(get_total_stake_amount=lambda: 1500)
        self.assertAlmostEqual(stake(s), 600)
        self.assertEqual(s._peak_tradable_balance, 1500)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    artifact = {
        "scope": "offline rule/loader tests; no profitability backtest performed",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "successful": result.wasSuccessful(),
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(SOURCE.iterdir()) if p.suffix in (".py", ".json")},
        "test_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (Path(__file__).parent/"TEST_RESULTS.json").write_text(json.dumps(artifact, indent=2)+"\n")
    sys.exit(0 if result.wasSuccessful() else 1)
