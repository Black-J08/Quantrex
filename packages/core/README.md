# quantrex-core

Core abstractions and domain models for the Quantrex framework. Defines the trading primitives (candles, positions, strategy protocols, logging facade) consumed by the backtest and live trading packages.

## Installation

```bash
uv add quantrex-core
# or from workspace
uv sync
```

## Usage

```python
from quantrex_core.logging import get_logger
from quantrex_core.protocols import DataProvider, DataAdapter
from quantrex_core.models import Candle
```
