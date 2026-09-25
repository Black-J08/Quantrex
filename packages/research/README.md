# Quantrex Research

Quantitative research package for the Quantrex framework. Provides a standalone research subsystem for forward-return distribution analysis and other quantitative research tasks.

## Architecture

```
quantrex_research/
├── core/                    # Engine and abstract contracts
│   ├── engine.py           # ResearchEngine (concept-agnostic executor)
│   └── base.py             # ResearchComponent abstract interface
├── research_components/     # Isolated research concepts
│   └── forward_return/     # Forward Return Distribution
│       ├── component.py    # ForwardReturnComponent
│       ├── config.py       # ForwardReturnConfig
│       ├── models.py       # ForwardReturnEvent, ForwardReturnSeries, ForwardReturnResult
│       ├── calculator.py   # ForwardReturnCalculator
│       ├── aggregator.py   # ForwardReturnAggregator
│       └── visualization.py # Plot generation
└── utils/                   # Common cross-component utilities
    └── data_helpers.py     # Shared pandas/numpy utilities
```

## Core Principle

> **A research component declares what it observes and how it reacts to candles; `ResearchEngine` only orchestrates data and the research-component lifecycle.**

## Quick Start

```python
from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent
from quantrex_data.providers.zerodha_provider import ZerodhaDataProvider
from quantrex_data.adapters.zerodha_adapter import ZerodhaDataAdapter
from datetime import timedelta

class MyForwardReturnResearch(ForwardReturnComponent):
    def __init__(self):
        super().__init__(
            horizons=[timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15), 
                      timedelta(minutes=30), timedelta(minutes=60)]
        )
    
    def on_candle(self, candle) -> None:
        # Detect LONG/SHORT event using same patterns as backtest strategies
        if self._detect_breakout(candle):
            self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"reason": "breakout"})
        elif self._detect_breakdown(candle):
            self.emit_event(candle.symbol, OrderSide.SELL, candle.timestamp, {"reason": "breakdown"})

if __name__ == "__main__":
    research = MyForwardReturnResearch()
    engine = ResearchEngine(
        instruments=[InstrumentSpec(...)],
        research_components=[research],
        data_start="2024-01-01",
        data_end="2024-12-31",
    )
    engine.run()
    # Results written to output/research/MyForwardReturnResearch/<timestamp>/
```

## Output Artifacts

For each research component, the engine creates:
```
output/research/<ComponentClassName>/<timestamp>/
├── forward_returns.json      # Per-horizon statistics
├── forward_returns.csv       # Raw percentage returns
├── forward_returns.parquet   # Efficient binary (optional)
└── plots/
    ├── distribution_{horizon}.png    # Histogram + KDE + Normal overlay
    ├── qq_{horizon}.png              # Q-Q plot vs normal
    ├── tail_comparison_{horizon}.png # Positive vs negative tail comparison
    └── horizon_comparison.png        # Multi-horizon comparison
```

## Statistics Included

Per horizon: count, mean, median, std, min, max, quantiles (25/50/75/90/95/99), positive_prob, skewness, excess_kurtosis, VaR_95, CVaR_95, VaR_99, CVaR_99, tail_ratio

## Dependencies

- quantrex-core
- quantrex-data
- quantrex-backtest (for DataOrchestrator only)
- pandas, numpy, matplotlib