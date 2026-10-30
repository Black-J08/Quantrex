- use mongoDB with docker for cache and access_token rather than  
- support for OI
- no need of generate_cache_key
- add docs and examples
- running pytest opens up browser when testing auth flow, any way to avoid that?
- single IST timezone declaration needed
- market timing and calendar is defined per data vendor (brokers)
- cache resampled timeframe data with this order: check 45m timeframe cache -> 1m timeframe cache -> fetch from broker

- create desloppify-subagents agent and update the hindsight agent system prompt and skill with more usage of tools

- create kernel module -> research and backtest module -> live module (research, backtest and live shares the same strategy)


- cli support for commands
- use STOP and STOP LIMIT orders
- backup of the strategy/research file in the output directory so it can be run again
- show some kind of progress bar in backtest/research
- add support for futures and options from starting
- query based position manager with extra columns for strategy tracking
- add slippage and tax in backtest