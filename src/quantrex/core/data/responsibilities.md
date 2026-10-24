# Responsibilities of `broker/` vs `data/`

**`broker/` talks to vendors. `data/` turns what vendors return into clean, canonical market data for the rest of the system.**

## `data/`: market data service

It treats brokers as interchangeable sources and owns everything about the data itself.

- **Storage and caching:** Feather files on disk, so you fetch once and read locally afterward
- **Data quality:** dedupe, gap detection, market calendar and session awareness, corporate-action adjustments, sanity checks
- **Transformations:** tick to bar aggregation, resampling (1m to 5m/1d)
- **Live feed management:** subscriptions, reconnect and resubscribe, building bars from ticks, fan-out to multiple consumers (strategy, recorder, UI)
- **Consumer-facing API:** `get_bars(symbol, timeframe, start, end)` and `subscribe(symbols, on_bar)`

It does **not** do order placement, auth flows, or vendor HTTP details.

## Where the line blurs

| Concern | Put it in | Why |
|---|---|---|
| Downloading the instrument dump | `broker/` | Vendor-specific format and endpoint |
| Parsing it into canonical instruments | `data/` | Cross-broker mapping is a domain concern |
| Max 60 days per request | `broker/` declares the limit, `data/` does the chunking | Vendor fact vs. orchestration logic |
| Websocket connect/reconnect | `broker/` (connection), `data/` (resubscribe, bar continuity) | Transport vs. feed semantics |
| Rate limiting | `broker/` enforces its own, `data/` schedules work sensibly | Each vendor protects itself |

**Litmus test:** if you swapped Zerodha for Dhan, only `broker/` should change. If you changed from Feather to a database or from 1m to tick bars, only `data/` should change.
