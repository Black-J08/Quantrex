"""Backtest engine core orchestration."""

from datetime import datetime, timezone
from pathlib import Path
import csv
from loguru import logger

from quantrex_core.models import Candle
from quantrex_core.protocols import DataAdapter
from quantrex_core.strategy.base import Strategy
from quantrex_core.position.manager import PositionManager
from .context import BacktestStrategyContext
from ..exceptions.backtest_error import ProviderError


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy's lifecycle methods for each candle.

    Example:
        >>> from quantrex_data.providers.csv_provider import CSVDataProvider
        >>> from quantrex_data.adapters.csv_adapter import CSVDataAdapter
        >>> from quantrex_backtest import BacktestEngine
        >>> from quantrex_core import Strategy, Candle
        >>>
        >>> class MyStrategy(Strategy):
        ...     def on_candle(self, candle: Candle) -> None:
        ...         print(candle.timestamp, candle.close)
        >>>
        >>> provider = CSVDataProvider("data.csv", has_header=False)
        >>> adapter = CSVDataAdapter(provider, mapping={...})
        >>> strategy = MyStrategy()
        >>> engine = BacktestEngine(adapter, strategy, symbol="COPPER")
        >>> engine.run()
    """

    def __init__(
        self,
        adapter: DataAdapter,
        strategy: Strategy,
        symbol: str = "",
        datetime_format: str = "%Y%m%d %H:%M",
    ) -> None:
        """Initialize the backtest engine.

        Args:
            adapter: DataAdapter instance providing normalized candle data via read()
            strategy: Strategy instance to execute
            symbol: Trading symbol for the candles
            datetime_format: Format string for parsing datetime from adapter data

        Raises:
            ProviderError: If adapter is None or strategy is None.
        """
        if adapter is None:
            raise ProviderError("DataAdapter is required; received None")
        if strategy is None:
            raise ProviderError("Strategy is required; received None")

        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._datetime_format = datetime_format

        # Create PositionManager and StrategyContext
        self._position_manager = PositionManager()
        self._context = BacktestStrategyContext(self._position_manager, datetime.min)
        
        # Inject context into Strategy
        self._strategy.set_context(self._context)

    def run(self) -> None:
        """Run the backtest, invoking the strategy's lifecycle methods.

        Calls strategy.on_start(), then strategy.on_candle() for each candle
        in timestamp order, then strategy.on_stop().
        After completion, exports closed trades to CSV.

        Raises:
            ProviderError: If adapter.read() fails or returns invalid data.
        """
        backtest_start_utc = datetime.now(timezone.utc)
        logger.info("Starting backtest for symbol: {}", self._symbol)

        self._strategy.on_start()

        try:
            raw_data = self._adapter.read()
        except Exception as e:
            logger.exception("Adapter read() failed")
            raise ProviderError(f"Failed to read data from adapter: {e}") from e

        if not raw_data:
            logger.warning("No data returned from adapter; backtest completed with zero candles")
            self._strategy.on_stop()
            self._export_trades_csv(backtest_start_utc, None, None)
            return

        # Sort by datetime for deterministic ordering
        raw_data.sort(key=lambda row: row.get("datetime", ""))

        logger.info("Processing {} candles", len(raw_data))

        data_start = None
        data_end = None

        for idx, row in enumerate(raw_data):
            try:
                candle = Candle.from_row(row, self._symbol, self._datetime_format)
                
                # Capture first and last candle timestamps for output path
                if data_start is None:
                    data_start = candle.timestamp.strftime("%Y%m%d_%H%M%S")
                data_end = candle.timestamp.strftime("%Y%m%d_%H%M%S")
                
                # Update context time and candle for order timestamps and pricing
                self._context.update_time(candle.timestamp)
                self._context.update_candle(candle)
                self._strategy.on_candle(candle)
            except Exception as e:
                logger.exception("Failed to process candle at index {}", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        self._strategy.on_stop()
        logger.success("Backtest completed: {} candles processed", len(raw_data))

        # Export closed trades to CSV
        self._export_trades_csv(backtest_start_utc, data_start, data_end)

    def _export_trades_csv(
        self,
        backtest_start_utc: datetime,
        data_start: str | None,
        data_end: str | None,
    ) -> None:
        """Export closed trades to CSV file."""
        trades = self._position_manager.get_closed_trades()
        
        # Build output path
        strategy_name = type(self._strategy).__name__
        backtest_start_str = backtest_start_utc.strftime("%Y%m%d_%H%M%S")
        
        if data_start is None or data_end is None:
            data_start = backtest_start_str
            data_end = backtest_start_str
        
        output_dir = Path("output") / "backtest" / strategy_name / f"{backtest_start_str}_{self._symbol}_{data_start}_{data_end}_short"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / "closed_trades.csv"
        
        # Write CSV with headers (even if empty)
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "symbol", "side", "quantity", 
                "entry_timestamp", "entry_price", 
                "exit_timestamp", "exit_price", 
                "pnl"
            ])
            for trade in trades:
                writer.writerow([
                    trade.symbol,
                    trade.side.value,
                    trade.quantity,
                    trade.entry_timestamp.isoformat(),
                    trade.entry_price,
                    trade.exit_timestamp.isoformat(),
                    trade.exit_price,
                    trade.pnl,
                ])
        
        logger.info("Exported {} closed trades to {}", len(trades), output_file)