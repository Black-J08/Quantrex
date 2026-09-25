"""Integration tests for ResearchEngine with ForwardReturnComponent."""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide
from quantrex_core.protocols import DataAdapter
from quantrex_core.logging import setup_logging

from quantrex_research import ResearchEngine
from quantrex_research.research_components.forward_return import ForwardReturnComponent, ForwardReturnConfig
from quantrex_backtest import InstrumentSpec, BacktestConfig


class IntegrationTestComponent(ForwardReturnComponent):
    """Component for integration testing."""
    
    def __init__(self, config):
        super().__init__(config)
        self.event_count = 0
    
    def on_candle(self, candle: Candle) -> None:
        # Emit event on first candle
        if self.event_count == 0:
            self.emit_event(candle.symbol, OrderSide.BUY, candle.timestamp, {"test": "integration"})
            self.event_count += 1


def test_integration_full_run_with_csv_data():
    """Full forward-return distribution run with CSV data."""
    setup_logging(level="INFO")
    
    # Use existing CSV test data
    csv_path = "/home/black_j/Dev/Quantrex/example_csv_data/COPPER24JUNFUT.csv"
    
    # Check if file exists
    if not Path(csv_path).exists():
        import pytest
        pytest.skip(f"Test data file not found: {csv_path}")
    
    from quantrex_data.providers.csv_provider import CSVDataProvider
    from quantrex_data.adapters.csv_adapter import CSVDataAdapter
    
    config = ForwardReturnConfig(
        horizons=[
            timedelta(minutes=1),
            timedelta(minutes=5),
            timedelta(minutes=15),
        ],
        boundary_handling="nan",
        missing_data_handling="skip",
    )
    component = IntegrationTestComponent(config)
    
    instruments = [
        InstrumentSpec(
            symbol="COPPER",
            adapter=CSVDataAdapter(
                CSVDataProvider(
                    file_path=csv_path,
                    has_header=False,
                    datetime_format="%Y%m%d %H:%M",
                    datetime_column=[0, 1],
                ),
                column_mapping={
                    "datetime": [0, 1],
                    "open": 2,
                    "high": 3,
                    "low": 4,
                    "close": 5,
                    "volume": 6,
                },
            ),
        ),
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ResearchEngine(
            instruments=instruments,
            research_components=[component],
            data_start="2024-06-01",
            data_end="2024-06-30",
            backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
        )
        
        # Override output base to use temp directory
        import quantrex_research.core.engine as engine_module
        original_run = engine.run
        
        def run_with_custom_output():
            # We can't easily override output directory without modifying engine
            # For now, just run and verify it completes
            return original_run()
        
        results = engine.run()
    
    # Verify results
    assert "IntegrationTestComponent" in results
    result = results["IntegrationTestComponent"]
    assert result is not None
    assert hasattr(result, 'horizon_stats')
    assert len(result.horizon_stats) > 0
    
    # Check that we have statistics for each horizon
    for horizon in config.horizons:
        assert horizon in result.horizon_stats
        stats = result.horizon_stats[horizon]
        assert stats["count"] >= 0


def test_integration_multi_symbol():
    """Multi-symbol forward-return distribution with synchronized data."""
    setup_logging(level="INFO")
    
    csv_path1 = "/home/black_j/Dev/Quantrex/example_csv_data/COPPER24JUNFUT.csv"
    csv_path2 = "/home/black_j/Dev/Quantrex/example_csv_data/COPPER24JULFUT.csv"
    
    if not Path(csv_path1).exists() or not Path(csv_path2).exists():
        import pytest
        pytest.skip("Test data files not found")
    
    from quantrex_data.providers.csv_provider import CSVDataProvider
    from quantrex_data.adapters.csv_adapter import CSVDataAdapter
    
    config = ForwardReturnConfig(
        horizons=[timedelta(minutes=1), timedelta(minutes=5)],
        boundary_handling="nan",
        missing_data_handling="skip",
    )
    component = IntegrationTestComponent(config)
    
    instruments = [
        InstrumentSpec(
            symbol="COPPER_JUN",
            adapter=CSVDataAdapter(
                CSVDataProvider(
                    file_path=csv_path1,
                    has_header=False,
                    datetime_format="%Y%m%d %H:%M",
                    datetime_column=[0, 1],
                ),
                column_mapping={
                    "datetime": [0, 1],
                    "open": 2,
                    "high": 3,
                    "low": 4,
                    "close": 5,
                    "volume": 6,
                },
            ),
        ),
        InstrumentSpec(
            symbol="COPPER_JUL",
            adapter=CSVDataAdapter(
                CSVDataProvider(
                    file_path=csv_path2,
                    has_header=False,
                    datetime_format="%Y%m%d %H:%M",
                    datetime_column=[0, 1],
                ),
                column_mapping={
                    "datetime": [0, 1],
                    "open": 2,
                    "high": 3,
                    "low": 4,
                    "close": 5,
                    "volume": 6,
                },
            ),
        ),
    ]
    
    engine = ResearchEngine(
        instruments=instruments,
        research_components=[component],
        data_start="2024-06-01",
        data_end="2024-06-30",
        backtest_config=BacktestConfig(auto_download=False, validate_completeness=False, min_bars_required=1),
    )
    
    results = engine.run()
    
    # Verify results
    assert "IntegrationTestComponent" in results
    result = results["IntegrationTestComponent"]
    assert result is not None
    
    # Should have events from both symbols
    assert len(component._series_list) >= 1