# Responsibilities

Engine owns Kernel. Kernel owns Strategy. Each layer talks only to the layer directly beneath it.

## Engine
The only layer that differs between research, backtest, and live.
- Creates, starts, and stops the kernel
- Input: sources data and hands it to the kernel
- Output: decides what to do with what the kernel emits
  - Live: place orders
  - Backtest / research: write to the trade log file
- Does not run the clock, hold strategy state, or make trading decisions

## Kernel
The same in every mode; unaware of whether it is live, backtesting, or researching.
- Runs the event loop, accepting input as a stream or a loop and treating both identically
- Runs the clock (the single source of "now")
- Manages the strategy's internal state
- Passes the strategy's decisions outward
- Does not know where data comes from or where outputs go

## Strategy
The only layer researchers write: a simple computational and conditional interface.
- Decision logic only
- No I/O, no clock, no state lifecycle, no awareness of mode

## Rules
- A strategy is written once and runs unchanged in research, backtest, and live
- Only the engine changes between modes
- Dependencies point downward only
- MVP-minimal: no abstraction until a second use demands it