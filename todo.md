- seperate token bucket rate limiter in core/ module
- async historical chunk with rate limiter for speedy download
- update framework timeframe to zerodha timeframe management as it can also be odd
- use mongoDB with docker for cache and access_token rather than  
- support for all timeframe by resampling from 1-minute data or 1-day data
- support for OI
- no need of generate_cache_key
- add docs and examples
- timeframe should not be pre defined anywhere as 1 minute and 1 day (that's all needed) data can be resampled to any timeframe needed
- fix ruff issues in tests/ and examples/



Older (not checked what is still valid)

- make volume and open interest optional
- cli support for commands
- use STOP and STOP LIMIT orders
- backup of the strategy file so it can be run again
- show some kind of progress bar in backtest
- add support for custom timeframe where the need for resampling arises
- redundancy like token bucket limiter
- every packages review
- dhan and zerodha should have same parameters 
- query based position manager with extra columns for strategy tracking
- find better alternative to protocols
- reduce redundancy
- introduce timeframe in Candle dataclass
- add slippage and tax in backtest
- seperate analytics from the backtest and portfolio coupling right now
- see what nse calendar is in data orchestration class
- it is not the responsibility of the data provider to format data before, adapter will normalise it before use. store the cache as raw like response so there's less complexity
- centralised configuration with a root level config at ~/.quantrex/.env with the option to overide with .env in the project directory
- make the engine more robust and picking short focus at a time
- if data cache is hit there is no need of to hit the authentication
- give access to closed trades to check something
- add exit reason and entry reason to also come in the trade sheet