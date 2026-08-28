"""Integration tests for Dhan provider with BacktestEngine."""

import pytest
from unittest.mock import Mock, patch
from datetime import date

from quantrex_data.providers.dhan_provider import DhanDataProvider
from quantrex_data.adapters.dhan_adapter import DhanDataAdapter
from quantrex_backtest import BacktestEngine
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
        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client, \
             patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock_master:

            # Setup mock client
            client_instance = Mock()
            mock_client.return_value = client_instance
            client_instance.get_daily_historical.return_value = Mock(
                model_dump=lambda **kwargs: MOCK_DAILY_HISTORICAL_RESPONSE
            )

            # Setup mock instrument master
            master_instance = Mock()
            mock_master.return_value = master_instance
            master_instance.resolve_symbol.return_value = "1333"

            provider = DhanDataProvider(
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-05",
                timeframe="day",
            )
            yield provider

    def test_provider_adapter_engine_flow(self, mock_provider):
        """Test complete flow: Provider -> Adapter -> Engine."""
        # Create adapter
        adapter = DhanDataAdapter(mock_provider)

        # Create strategy and engine - use Dhan's datetime format
        strategy = TestStrategy()
        engine = BacktestEngine(adapter, strategy, symbol="RELIANCE", datetime_format="%Y-%m-%d %H:%M:%S")

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
        engine = BacktestEngine(adapter, strategy, symbol="RELIANCE", datetime_format="%Y-%m-%d %H:%M:%S")

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
        """Test adapter with custom timezone (IST)."""
        adapter = DhanDataAdapter(mock_provider, timezone="Asia/Kolkata")
        data = adapter.read()

        # 1704067200 UTC = 2024-01-01 05:30:00 IST
        assert data[0]["datetime"] == "2024-01-01 05:30:00"

    def test_provider_with_date_objects(self):
        """Test provider initialization with date/datetime objects."""
        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client, \
             patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock_master:

            client_instance = Mock()
            mock_client.return_value = client_instance
            client_instance.get_daily_historical.return_value = Mock(
                model_dump=lambda **kwargs: MOCK_DAILY_HISTORICAL_RESPONSE
            )

            master_instance = Mock()
            mock_master.return_value = master_instance
            master_instance.resolve_symbol.return_value = "1333"

            provider = DhanDataProvider(
                security_id="1333",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date=date(2024, 1, 1),
                to_date=date(2024, 1, 5),
                timeframe="day",
            )

            adapter = DhanDataAdapter(provider)
            data = adapter.read()

            assert len(data) == 5

    def test_provider_with_intraday_timeframe(self):
        """Test provider with intraday timeframe."""
        from quantrex_test_support.dhan import MOCK_INTRADAY_HISTORICAL_RESPONSE

        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client, \
             patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock_master:

            client_instance = Mock()
            mock_client.return_value = client_instance
            client_instance.get_intraday_historical.return_value = Mock(
                model_dump=lambda **kwargs: MOCK_INTRADAY_HISTORICAL_RESPONSE
            )

            master_instance = Mock()
            mock_master.return_value = master_instance
            master_instance.resolve_symbol.return_value = "1333"

            provider = DhanDataProvider(
                security_id="1333",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01 09:15:00",
                to_date="2024-01-01 09:20:00",
                timeframe="1minute",
            )

            adapter = DhanDataAdapter(provider)
            data = adapter.read()

            assert len(data) == 5
            # Check intraday timestamps have time component
            assert " " in data[0]["datetime"]
            assert ":" in data[0]["datetime"]

    def test_chunking_integration(self):
        """Test provider chunking with multiple API calls."""
        from quantrex_test_support.dhan import MOCK_DAILY_HISTORICAL_RESPONSE

        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client, \
             patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock_master:

            client_instance = Mock()
            mock_client.return_value = client_instance

            # Create three chunk responses using proper model objects
            # 10 days (Jan 1-10) with 3-day chunks = 3 chunks: 1-4 (4 days), 5-8 (4 days), 9-10 (2 days)
            from quantrex_data.providers.dhan_provider.models import HistoricalDataResponse

            chunk1 = HistoricalDataResponse(
                open=[2500.0, 2510.0, 2520.0, 2515.0],
                high=[2520.0, 2525.0, 2535.0, 2525.0],
                low=[2490.0, 2505.0, 2510.0, 2500.0],
                close=[2510.0, 2520.0, 2515.0, 2530.0],
                volume=[100000, 150000, 120000, 180000],
                timestamp=[1704067200, 1704153600, 1704240000, 1704326400],
                open_interest=[50000, 55000, 52000, 58000],
            )
            chunk2 = HistoricalDataResponse(
                open=[2530.0, 2525.0, 2535.0, 2530.0],
                high=[2540.0, 2535.0, 2545.0, 2540.0],
                low=[2520.0, 2515.0, 2525.0, 2520.0],
                close=[2535.0, 2530.0, 2540.0, 2535.0],
                volume=[200000, 190000, 210000, 220000],
                timestamp=[1704412800, 1704499200, 1704585600, 1704672000],
                open_interest=[60000, 59000, 61000, 62000],
            )
            chunk3 = HistoricalDataResponse(
                open=[2540.0, 2545.0],
                high=[2550.0, 2555.0],
                low=[2530.0, 2535.0],
                close=[2545.0, 2550.0],
                volume=[230000, 240000],
                timestamp=[1704758400, 1704844800],
                open_interest=[63000, 64000],
            )
            client_instance.get_daily_historical.side_effect = [chunk1, chunk2, chunk3]

            master_instance = Mock()
            mock_master.return_value = master_instance
            master_instance.resolve_symbol.return_value = "1333"

            provider = DhanDataProvider(
                security_id="1333",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-10",
                timeframe="day",
                chunk_size_days={"day": 3, "1minute": 30, "5minute": 60, "15minute": 180, "30minute": 360, "60minute": 720},
            )

            adapter = DhanDataAdapter(provider)
            data = adapter.read()

            # Should have merged 10 candles from 3 chunks (4+4+2)
            assert len(data) == 10
            assert client_instance.get_daily_historical.call_count == 3


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
        with patch("quantrex_data.providers.dhan_provider.provider.DhanAPIClient") as mock_client, \
             patch("quantrex_data.providers.dhan_provider.provider.InstrumentMaster") as mock_master:
            client_instance = Mock()
            mock_client.return_value = client_instance
            client_instance.get_daily_historical.return_value = Mock(
                model_dump=lambda **kwargs: MOCK_DAILY_HISTORICAL_RESPONSE
            )
            master_instance = Mock()
            mock_master.return_value = master_instance
            master_instance.resolve_symbol.return_value = "1333"
            provider = DhanDataProvider(
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date="2024-01-01",
                to_date="2024-01-05",
                timeframe="day",
            )
            yield provider

    def test_engine_must_match_adapter_datetime_format(self, mock_provider):
        """Pass-through with matching formats: engine consumes adapter output successfully."""
        # Sanity check: the default adapter output uses the ISO-like format.
        adapter = DhanDataAdapter(mock_provider)  # default "%Y-%m-%d %H:%M:%S"
        first_row = adapter.read()[0]
        assert first_row["datetime"].count("-") == 2  # ISO-like: 2024-01-01 00:00:00
        assert first_row["datetime"].count(":") == 2  # HH:MM:SS

    def test_engine_with_mismatched_format_fails(self, mock_provider):
        """Default BacktestEngine ("%Y%m%d %H:%M") cannot parse the adapter's output."""
        adapter = DhanDataAdapter(mock_provider)
        strategy = TestStrategy()
        engine = BacktestEngine(adapter, strategy, symbol="RELIANCE")  # engine default

        from quantrex_backtest.exceptions.backtest_error import ProviderError

        with pytest.raises(ProviderError, match="Failed to process candle"):
            engine.run()

    def test_engine_with_matching_format_succeeds(self, mock_provider):
        """When both adapter and engine use "%Y-%m-%d %H:%M:%S", the backtest runs cleanly."""
        adapter = DhanDataAdapter(mock_provider, datetime_format="%Y-%m-%d %H:%M:%S")
        strategy = TestStrategy()
        engine = BacktestEngine(
            adapter, strategy, symbol="RELIANCE", datetime_format="%Y-%m-%d %H:%M:%S"
        )

        engine.run()

        assert strategy.started
        assert strategy.stopped
        assert len(strategy.candles) == 5
        assert strategy.candles[0].timestamp.year == 2024
        assert strategy.candles[0].timestamp.month == 1
        assert strategy.candles[0].timestamp.day == 1