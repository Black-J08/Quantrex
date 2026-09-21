"""Integration tests for Dhan provider with BacktestEngine."""

import pytest
from unittest.mock import Mock

from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine, InstrumentSpec, PortfolioConfig
from quantrex_core.strategy.base import Strategy
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_test_support.dhan import MOCK_DAILY_HISTORICAL_RESPONSE


class TestStrategy(Strategy):
    """Test strategy that records received candles."""

    def __init__(self):
        super().__init__()
        self.candles = []
        self.started = False
        self.stopped = False

    def on_start(self) -> None:
        self.started = True

    def on_candle(self, candle: Candle) -> None:
        self.candles.append(candle)

    def on_stop(self) -> None:
        self.stopped = True


class TestDhanIntegration:
    """Integration tests for DhanDataProvider -> DhanDataAdapter -> BacktestEngine flow."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock DhanDataProvider."""
        provider = Mock(spec=DhanDataProvider)
        provider.fetch = Mock(side_effect=lambda timeframe=None, from_date=None, to_date=None: MOCK_DAILY_HISTORICAL_RESPONSE)
        provider.supported_timeframes_property = ["1M", "5M", "15M", "30M", "1H", "1D"]
        provider.close = Mock()
        yield provider

    def test_provider_adapter_engine_flow(self, mock_provider):
        """Test complete flow: Provider -> Adapter -> Engine."""
        # Create adapter
        adapter = DhanDataAdapter(mock_provider)

        # Create strategy and engine - adapter owns the datetime format
        strategy = TestStrategy()
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=adapter)]
        config = PortfolioConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        engine = BacktestEngine(instruments, strategy, config)

        # Run backtest
        engine.run()

        # Verify strategy received candles
        assert strategy.started
        assert strategy.stopped
        assert len(strategy.candles) == 5

        # Verify candle data
        first_candle = strategy.candles[0]
        assert isinstance(first_candle, Candle)
        assert first_candle.symbol == "RELIANCE"
        assert first_candle.open == 2500.0
        assert first_candle.high == 2520.0
        assert first_candle.low == 2490.0
        assert first_candle.close == 2510.0
        assert first_candle.volume == 100000

    def test_provider_adapter_engine_with_orders(self, mock_provider):
        """Test flow with order submission."""
        class OrderStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.orders = []
                self.candles = []

            def on_candle(self, candle: Candle) -> None:
                if len(self.candles) == 0:
                    order = self.ctx.submit_order(
                        symbol=candle.symbol,
                        side=OrderSide.BUY,
                        quantity=10.0,
                    )
                    self.orders.append(order)
                self.candles.append(candle)

        adapter = DhanDataAdapter(mock_provider)
        strategy = OrderStrategy()
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=adapter)]
        config = PortfolioConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        engine = BacktestEngine(instruments, strategy, config)

        engine.run()

        assert len(strategy.candles) == 5
        assert len(strategy.orders) == 1
        assert strategy.orders[0].side == OrderSide.BUY
        assert strategy.orders[0].quantity == 10.0

    def test_adapter_with_custom_datetime_format(self, mock_provider):
        """Test adapter with custom datetime format."""
        adapter = DhanDataAdapter(mock_provider, datetime_format="%Y/%m/%d")
        data = adapter.read()

        assert data[0]["datetime"] == "2024/01/01"

    def test_adapter_with_custom_timezone(self, mock_provider):
        """Test adapter with custom timezone (IST is the default)."""
        adapter = DhanDataAdapter(mock_provider, timezone="Asia/Kolkata")
        data = adapter.read()

        # Mock epoch 1704047400 == 2024-01-01 00:00:00 IST.
        assert data[0]["datetime"] == "2024-01-01 00:00:00"

    def test_provider_with_date_objects(self, mock_provider):
        """Test provider initialization with date/datetime objects."""
        adapter = DhanDataAdapter(mock_provider)
        data = adapter.read()

        assert len(data) == 5

    def test_provider_with_intraday_timeframe(self, mock_provider):
        """Test provider with intraday timeframe."""
        adapter = DhanDataAdapter(mock_provider)
        data = adapter.read()

        assert len(data) == 5
        # Check intraday timestamps have time component
        assert " " in data[0]["datetime"]
        assert ":" in data[0]["datetime"]

    def test_chunking_integration(self, mock_provider):
        """Test provider chunking with multiple API calls."""
        adapter = DhanDataAdapter(mock_provider)
        data = adapter.read()

        assert len(data) == 5


class TestDhanExampleStrategyDatetimeFormat:
    """Regression: BacktestEngine must parse the datetime format the adapter emits.

    ``dhan_example_strategy.py`` configures ``DhanDataAdapter`` with
    ``datetime_format="%Y-%m-%d %H:%M:%S"`` (Dhan's ISO-like default). If the
    ``BacktestEngine`` is left at its default (``"%Y%m%d %H:%M"``), the engine
    raises ``ValueError`` on the first candle - this guards the example.
    """

    @pytest.fixture
    def mock_provider(self):
        """Local copy of the mock-provider fixture for this class."""
        provider = Mock(spec=DhanDataProvider)
        provider.fetch = Mock(side_effect=lambda timeframe=None, from_date=None, to_date=None: MOCK_DAILY_HISTORICAL_RESPONSE)
        provider.supported_timeframes_property = ["1M", "5M", "15M", "30M", "1H", "1D"]
        provider.close = Mock()
        yield provider

    def test_engine_must_match_adapter_datetime_format(self, mock_provider):
        """Pass-through with matching formats: engine consumes adapter output successfully."""
        # Sanity check: the default adapter output uses the ISO-like format.
        adapter = DhanDataAdapter(mock_provider)  # default "%Y-%m-%d %H:%M:%S"
        first_row = adapter.read()[0]
        assert first_row["datetime"].count("-") == 2  # ISO-like: 2024-01-01 00:00:00
        assert first_row["datetime"].count(":") == 2  # HH:MM:SS

    def test_engine_with_mismatched_format_fails(self, mock_provider):
        """Mismatch is impossible: engine reads format from adapter (single source of truth).

        Before the fix, passing a different ``datetime_format`` to the
        engine than the adapter produced caused ``Candle.from_row`` to
        fail. After the fix, the engine reads ``adapter.datetime_format``
        directly, so no duplicate configuration exists and mismatch is
        impossible by architecture.
        """
        adapter = DhanDataAdapter(mock_provider)
        strategy = TestStrategy()
        # Engine no longer accepts datetime_format; it reads from adapter.
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=adapter)]
        config = PortfolioConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        engine = BacktestEngine(instruments, strategy, config)
        # Should succeed because adapter and engine agree automatically.
        engine.run()
        assert strategy.started
        assert len(strategy.candles) == 5

    def test_engine_with_matching_format_succeeds(self, mock_provider):
        """When both adapter and engine use "%Y-%m-%d %H:%M:%S", the backtest runs cleanly."""
        adapter = DhanDataAdapter(mock_provider, datetime_format="%Y-%m-%d %H:%M:%S")
        strategy = TestStrategy()
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=adapter)]
        config = PortfolioConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        engine = BacktestEngine(instruments, strategy, config)

        engine.run()

        assert strategy.started
        assert strategy.stopped
        assert len(strategy.candles) == 5
        assert strategy.candles[0].timestamp.year == 2024
        assert strategy.candles[0].timestamp.month == 1
        assert strategy.candles[0].timestamp.day == 1


class TestDhanClosedTradesTimestampRegression:
    """Regression: ``closed_trades.csv`` must record market time, not 18:30.

    Original defect (user-reported): every entry/exit timestamp in the
    exported ``closed_trades.csv`` showed ``T18:30:00``, i.e. the IST
    equivalent of 13:00 UTC and well after the 15:30 IST market close.
    Root cause: ``DhanDataAdapter`` interpreted Dhan's epoch-seconds as
    UTC even though Dhan's server (and the official ``dhanhq-py`` SDK)
    emits them in IST. Daily candles were therefore rendered at
    18:30 UTC and the engine wrote that wall clock into every trade
    record.

    This test runs the full pipeline (provider -> adapter -> engine ->
    CSV export) and asserts that every recorded timestamp matches the
    IST market clock the user actually saw on the exchange.
    """

    @pytest.fixture
    def mock_provider(self):
        provider = Mock(spec=DhanDataProvider)
        provider.fetch = Mock(side_effect=lambda timeframe=None, from_date=None, to_date=None: MOCK_DAILY_HISTORICAL_RESPONSE)
        provider.supported_timeframes_property = ["1M", "5M", "15M", "30M", "1H", "1D"]
        provider.close = Mock()
        yield provider

    def test_exported_trades_use_market_clock_not_18_30(self, mock_provider, tmp_path, monkeypatch):
        """Full pipeline: provider -> adapter -> engine -> CSV export.

        Verifies that entry/exit timestamps in closed_trades.csv match
        the IST market clock (not 18:30 UTC).
        """
        monkeypatch.chdir(tmp_path)

        class BuyAndSellStrategy(Strategy):
            """Open long on candle 0, close on candle 1 → exactly one closed trade."""

            def __init__(self) -> None:
                super().__init__()
                self._seen = 0

            def on_candle(self, candle: Candle) -> None:
                self._seen += 1
                if self._seen == 1:
                    self.ctx.submit_order(symbol=candle.symbol, side=OrderSide.BUY, quantity=10.0)
                elif self._seen == 2:
                    pos = self.ctx.get_position(candle.symbol)
                    if pos.quantity > 0:
                        self.ctx.submit_order(symbol=candle.symbol, side=OrderSide.SELL, quantity=pos.quantity)

        adapter = DhanDataAdapter(mock_provider, datetime_format="%Y-%m-%d %H:%M:%S")
        instruments = [InstrumentSpec(symbol="RELIANCE", adapter=adapter)]
        config = PortfolioConfig(auto_download=False, validate_completeness=False, min_bars_required=1)
        engine = BacktestEngine(instruments, BuyAndSellStrategy(), config)
        engine.run()

        # Locate the CSV the engine just wrote.
        csv_paths = list(tmp_path.rglob("closed_trades.csv"))
        assert csv_paths, "BacktestEngine did not write closed_trades.csv"
        csv_text = csv_paths[0].read_text()
        assert "RELIANCE,LONG,10.0" in csv_text

        # The first row of the mock represents 2024-01-01 00:00:00 IST.
        # The second row represents 2024-01-02 00:00:00 IST.
        #
        # T+1 execution timing:
        #   - BUY submitted during candle 0 (2024-01-01) → filled at candle 1 open (2024-01-02, price 2510)
        #   - SELL submitted during candle 1 (2024-01-02) → filled at candle 2 open (2024-01-03, price 2520)
        #   - entry_timestamp = 2024-01-02T00:00:00 (candle 1), exit_timestamp = 2024-01-03T00:00:00 (candle 2)
        #
        # With the IST-as-UTC bug, both would appear as 18:30 of the *previous*
        # UTC day (2023-12-31 18:30 / 2024-01-01 18:30).
        first_line = csv_text.splitlines()[1]
        entry_ts = first_line.split(",")[3]
        exit_ts = first_line.split(",")[5]

        assert entry_ts == "2024-01-02T00:00:00", (
            f"entry_timestamp={entry_ts!r}; expected 2024-01-02T00:00:00 IST "
            f"(T+1 fill: BUY on 2024-01-01 filled at candle 1 open)."
        )
        assert exit_ts == "2024-01-03T00:00:00", (
            f"exit_timestamp={exit_ts!r}; expected 2024-01-03T00:00:00 IST "
            f"(T+1 fill: SELL on 2024-01-02 filled at candle 2 open)."
        )
        # Explicit negative assertion: the buggy 18:30 suffix must be absent.
        for line in csv_text.splitlines()[1:]:
            assert "18:30" not in line, f"Buggy 18:30 timestamp found in CSV: {line}"
            for ts in (line.split(",")[3], line.split(",")[5]):
                assert "T18:30:00" not in ts, (
                    f"Found the 18:30 IST-as-UTC bug in CSV row: {line!r}"
                )