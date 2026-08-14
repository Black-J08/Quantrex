"""Backtest engine core orchestration."""

from collections.abc import Callable
from loguru import logger

from ..feeders.data_feeder import DataFeeder
from ..models.candle import Candle
from ..exceptions.backtest_error import ProviderError


class BacktestEngine:
    """Deterministic event-driven backtest engine.

    Processes OHLCV candles sequentially in timestamp order,
    invoking a strategy callback for each candle.

    Example:
        >>> from quantrex_data.providers.csv_reader import CSVReader
        >>> from quantrex_backtest import BacktestEngine
        >>>
        >>> reader = CSVReader("data.csv", mapping={...})
        >>> engine = BacktestEngine(reader, symbol="COPPER")
        >>> engine.run(lambda candle: print(candle.timestamp, candle.close))
    """

    def __init__(
        self,
        feeder: DataFeeder,
        symbol: str = "",
        datetime_format: str = "%Y%m%d %H:%M",
    ) -> None:
        """Initialize the backtest engine.

        Args:
            feeder: DataFeeder instance providing candle data via read()
            symbol: Trading symbol for the candles
            datetime_format: Format string for parsing datetime from feeder data

        Raises:
            ProviderError: If feeder is None.
        """
        if feeder is None:
            raise ProviderError("DataFeeder is required; received None")

        self._feeder = feeder
        self._symbol = symbol
        self._datetime_format = datetime_format

    def run(self, on_candle: Callable[[Candle], None]) -> None:
        """Run the backtest, invoking on_candle for each candle in timestamp order.

        Args:
            on_candle: Callback function receiving each Candle sequentially.
                       Signature: on_candle(candle: Candle) -> None

        Raises:
            ProviderError: If feeder.read() fails or returns invalid data.
        """
        logger.info("Starting backtest for symbol: {}", self._symbol)

        try:
            raw_data = self._feeder.read()
        except Exception as e:
            logger.exception("Feeder read() failed")
            raise ProviderError(f"Failed to read data from feeder: {e}") from e

        if not raw_data:
            logger.warning("No data returned from feeder; backtest completed with zero candles")
            return

        # Sort by datetime for deterministic ordering
        raw_data.sort(key=lambda row: row.get("datetime", ""))

        logger.info("Processing {} candles", len(raw_data))

        for idx, row in enumerate(raw_data):
            try:
                candle = Candle.from_row(row, self._symbol, self._datetime_format)
                on_candle(candle)
            except Exception as e:
                logger.exception("Failed to process candle at index {}", idx)
                raise ProviderError(f"Failed to process candle at index {idx}: {e}") from e

        logger.success("Backtest completed: {} candles processed", len(raw_data))