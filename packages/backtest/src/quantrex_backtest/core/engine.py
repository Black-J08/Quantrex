"""Backtest engine core orchestration."""

from loguru import logger

from quantrex_core.models import Candle
from quantrex_core.protocols import DataFeeder
from quantrex_core.strategy.base import Strategy
from ..exceptions.backtest_error import ProviderError


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy's lifecycle methods for each candle.

    Example:
        >>> from quantrex_data.providers.csv_reader import CSVReader
        >>> from quantrex_backtest import BacktestEngine
        >>> from quantrex_core import Strategy, Candle
        >>>
        >>> class MyStrategy(Strategy):
        ...     def on_candle(self, candle: Candle) -> None:
        ...         print(candle.timestamp, candle.close)
        >>>
        >>> reader = CSVReader("data.csv", mapping={...})
        >>> strategy = MyStrategy()
        >>> engine = BacktestEngine(reader, strategy, symbol="COPPER")
        >>> engine.run()
    """

    def __init__(
        self,
        feeder: DataFeeder,
        strategy: Strategy,
        symbol: str = "",
        datetime_format: str = "%Y%m%d %H:%M",
    ) -> None:
        """Initialize the backtest engine.

        Args:
            feeder: DataFeeder instance providing candle data via read()
            strategy: Strategy instance to execute
            symbol: Trading symbol for the candles
            datetime_format: Format string for parsing datetime from feeder data

        Raises:
            ProviderError: If feeder is None or strategy is None.
        """
        if feeder is None:
            raise ProviderError("DataFeeder is required; received None")
        if strategy is None:
            raise ProviderError("Strategy is required; received None")

        self._feeder = feeder
        self._strategy = strategy
        self._symbol = symbol
        self._datetime_format = datetime_format

    def run(self) -> None:
        """Run the backtest, invoking the strategy's lifecycle methods.

        Calls strategy.on_start(), then strategy.on_candle() for each candle
        in timestamp order, then strategy.on_stop().

        Raises:
            ProviderError: If feeder.read() fails or returns invalid data.
        """
        logger.info("Starting backtest for symbol: {}", self._symbol)

        self._strategy.on_start()

        try:
            raw_data = self._feeder.read()
        except Exception as e:
            logger.exception("Feeder read() failed")
            raise ProviderError(f"Failed to read data from feeder: {e}") from e

        if not raw_data:
            logger.warning("No data returned from feeder; backtest completed with zero candles")
            self._strategy.on_stop()
            return

        # Sort by datetime for deterministic ordering
        raw_data.sort(key=lambda row: row.get("datetime", ""))

        logger.info("Processing {} candles", len(raw_data))

        for idx, row in enumerate(raw_data):
            try:
                candle = Candle.from_row(row, self._symbol, self._datetime_format)
                self._strategy.on_candle(candle)
            except Exception as e:
                logger.exception("Failed to process candle at index {}", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        self._strategy.on_stop()
        logger.success("Backtest completed: {} candles processed", len(raw_data))