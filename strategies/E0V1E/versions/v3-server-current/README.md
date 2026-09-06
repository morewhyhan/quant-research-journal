# V3 Server Current and 60/40 Research Variant

## Version mapping

| Directory/file | Meaning |
| --- | --- |
| E0V1E_v3.py | Copy of the strategy file used by the current server container |
| E0V1E_v3.json | Parameters used by the current server strategy |
| E0V1E_v3_equity60_reserve40.py | Local research variant based on the server current strategy |
| E0V1E_v3_equity60_reserve40.json | Parameters for the local 60/40 research variant |

The server container currently loads E0V1E_v3. No G3 or equity60/reserve40 strategy file was found on the server during the 2026-09-06 inspection. The 60/40 file in this directory is therefore a research replay, not a strategy currently running in production.

The SHA-256 of the copied server current source is:

a293d5c61d580c6753e1445679ccda606b7cc2c555443a76d12a42bd188ae547

## 60/40 position sizing

The research variant keeps the server current entry and exit logic and changes only realized-equity exposure:

- below 5% drawdown: 60% exposure;
- 5% to below 10% drawdown: 73.3333% exposure;
- 10% to below 20% drawdown: 86.6667% exposure;
- at or above 20% drawdown: 97% exposure.

The high-water mark is currently process-local and is not restart-persistent. It must be persisted before this variant can be considered production-ready.
