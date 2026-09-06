# V3 Original and 60/40 Research Variant

E0V1E_v3.py and E0V1E_v3.json are the repository V3 Original strategy and its parameters.

E0V1E_v3_original_equity60.py is a research-only sizing variant. It inherits the Original entry, exit, stoploss, and short-entry sizing logic, then caps exposure using a 60/40 reserve ladder. It does not change the trade signals, so its trade count and percentage EV should match the Original when run on the same data.

The 2025 server-source comparison is stored in backtest-results/v3-server-2025-full/.
