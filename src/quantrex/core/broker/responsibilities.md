# Responsibilities of `broker/` vs `data/`

**`broker/` talks to vendors. `data/` turns what vendors return into clean, canonical market data for the rest of the system.**

## `broker/`: vendor adapters

It knows everything vendor-specific and nothing about how the data gets used.

- Auth and session lifecycle (Zerodha access tokens, Dhan client tokens, refresh and expiry)
- Order operations: place, modify, cancel, order book, trades
- Account state: positions, holdings, margins
- Raw market-data endpoints: historical candle API, quotes, websocket tick stream, instrument dump download
- Vendor quirks: rate limits, request-size limits, error mapping into your own exception types, transport-level retries
- A common interface, so `ZerodhaBroker` and `DhanBroker` are interchangeable

It does **not** do caching, storage, resampling, gap-filling, symbol normalization across vendors, or any strategy logic.

## Where the line blurs

| Concern | Put it in | Why |
|---|---|---|
| Downloading the instrument dump | `broker/` | Vendor-specific format and endpoint |
| Parsing it into canonical instruments | `data/` | Cross-broker mapping is a domain concern |
| Max 60 days per request | `broker/` declares the limit, `data/` does the chunking | Vendor fact vs. orchestration logic |
| Websocket connect/reconnect | `broker/` (connection), `data/` (resubscribe, bar continuity) | Transport vs. feed semantics |
| Rate limiting | `broker/` enforces its own, `data/` schedules work sensibly | Each vendor protects itself |

**Litmus test:** if you swapped Zerodha for Dhan, only `broker/` should change. If you changed from parquet to a database or from 1m to tick bars, only `data/` should change.


