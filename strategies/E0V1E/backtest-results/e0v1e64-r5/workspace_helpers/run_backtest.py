#!/usr/bin/env python3
"""Wrapper to run freqtrade backtesting with offline DNS/market-data patches."""
import sys
import os

# Ensure we can import fix_dns from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fix_dns  # noqa: E402 - must be imported before freqtrade

from freqtrade.main import main

if __name__ == '__main__':
    sys.exit(main())
