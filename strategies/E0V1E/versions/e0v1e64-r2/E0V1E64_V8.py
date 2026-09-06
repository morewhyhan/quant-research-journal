"""V8 = V5 extension wrapped around the previously audited V1 short exit.

MRO is deliberate: V5.custom_exit calls V1.custom_exit, which supplies
direction-correct short CCI recovery and delegates long exits unchanged.
No current unclosed candle extremum from Trade.min_rate/max_rate is used
by the replacement short exit. It does not repair the engine's OHLC stop model.
"""
from E0V1E64_V5 import E0V1E64_V5
from E0V1E64_V1 import E0V1E64_V1


class E0V1E64_V8(E0V1E64_V5, E0V1E64_V1):
    pass
