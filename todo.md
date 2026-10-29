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

- create kernel module -> research and backtest module -> live module (research, backtest and live shares the same strategy)


- cli support for commands
- use STOP and STOP LIMIT orders
- backup of the strategy/research file in the output directory so it can be run again
- show some kind of progress bar in backtest/research
- add support for futures and options from starting
- query based position manager with extra columns for strategy tracking
- add slippage and tax in backtest