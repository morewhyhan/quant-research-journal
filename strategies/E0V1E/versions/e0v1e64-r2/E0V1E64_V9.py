"""V9 = frozen V5 exits plus the previously audited V4 stake multipliers.

short_1: 0.90x; short_new: 1.10x; long signals: unchanged.
Total stake remains capped by proposed available capital and exchange limits.
"""
from E0V1E64_V5 import E0V1E64_V5
from E0V1E64_V4 import E0V1E64_V4


class E0V1E64_V9(E0V1E64_V5, E0V1E64_V4):
    pass
