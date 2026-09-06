"""V6 = frozen V5, changing only the extension timeout from 60 to 120 minutes."""
from E0V1E64_V5 import E0V1E64_V5


class E0V1E64_V6(E0V1E64_V5):
    max_extension_minutes = 120
