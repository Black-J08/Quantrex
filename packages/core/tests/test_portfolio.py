"""Tests for PortfolioState model."""

from datetime import datetime

from quantrex_core.models import PortfolioState
from quantrex_core.models.position import Position


class TestPortfolioState:
    """Tests for PortfolioState model."""

    def test_empty_portfolio_state(self):
        """Test creating an empty portfolio state."""
        state = PortfolioState.empty()

        assert state.cash == 0.0
        assert state.equity == 0.0
        assert state.margin_used == 0.0
        assert state.margin_available == 0.0
        assert state.positions == {}
        assert state.unrealized_pnl == 0.0
        assert state.realized_pnl == 0.0

    def test_portfolio_state_with_values(self):
        """Test creating a portfolio state with values."""
        pos = Position(
            entry_timestamp=datetime(2026, 1, 1),
            entry_price=100.0,
            symbol="RELIANCE",
            quantity=10.0,
        )

        state = PortfolioState(
            cash=50000.0,
            equity=51000.0,
            margin_used=1000.0,
            margin_available=50000.0,
            positions={"RELIANCE": pos},
            unrealized_pnl=1000.0,
            realized_pnl=500.0,
        )

        assert state.cash == 50000.0
        assert state.equity == 51000.0
        assert state.margin_used == 1000.0
        assert state.margin_available == 50000.0
        assert "RELIANCE" in state.positions
        assert state.unrealized_pnl == 1000.0
        assert state.realized_pnl == 500.0

    def test_portfolio_state_immutable(self):
        """Test that PortfolioState is immutable (frozen)."""
        state = PortfolioState.empty()

        # Should not be able to modify fields
        try:
            state.cash = 100.0
            assert False, "Should have raised FrozenInstanceError"
        except Exception:
            pass  # Expected


class TestPositionSizerProtocol:
    """Tests for PositionSizer protocol."""

    def test_position_sizer_protocol(self):
        """Test that PositionSizer protocol can be implemented."""
        from quantrex_core.portfolio import PositionSizer
        from quantrex_core.models import PortfolioState

        class TestSizer:
            def compute_target_weights(
                self,
                portfolio: PortfolioState,
                signals: dict[str, float],
            ) -> dict[str, float]:
                return {symbol: 1.0 / len(signals) for symbol in signals}

        sizer = TestSizer()
        # Should be able to use as PositionSizer
        assert isinstance(sizer, PositionSizer)

        portfolio = PortfolioState.empty()
        signals = {"RELIANCE": 1.0, "TCS": -1.0}
        weights = sizer.compute_target_weights(portfolio, signals)

        assert weights["RELIANCE"] == 0.5
        assert weights["TCS"] == 0.5


class TestInstrumentSpec:
    """Tests for InstrumentSpec."""

    def test_instrument_spec_creation(self):
        """Test creating an InstrumentSpec."""
        from quantrex_core import InstrumentSpec
        from quantrex_core.protocols import DataAdapter
        from unittest.mock import Mock

        adapter = Mock(spec=DataAdapter)
        spec = InstrumentSpec(
            symbol="RELIANCE",
            adapter=adapter,
            data_path="/data/reliance.csv",
            timeframe_overrides={"1H": {}},
        )

        assert spec.symbol == "RELIANCE"
        assert spec.adapter == adapter
        assert spec.data_path == "/data/reliance.csv"
        assert spec.timeframe_overrides == {"1H": {}}

    def test_instrument_spec_defaults(self):
        """Test InstrumentSpec with default values."""
        from quantrex_core import InstrumentSpec
        from quantrex_core.protocols import DataAdapter
        from unittest.mock import Mock

        adapter = Mock(spec=DataAdapter)
        spec = InstrumentSpec(symbol="RELIANCE", adapter=adapter)

        assert spec.symbol == "RELIANCE"
        assert spec.adapter == adapter
        assert spec.data_path is None
        assert spec.timeframe_overrides is None


class TestPortfolioConfig:
    """Tests for PortfolioConfig."""

    def test_portfolio_config_defaults(self):
        """Test PortfolioConfig with default values."""
        from quantrex_core import PortfolioConfig

        config = PortfolioConfig()

        assert config.initial_cash == 1_000_000.0
        assert config.margin_requirement == 1.0
        assert config.position_sizer is None
        assert config.data_start is None
        assert config.data_end is None
        assert config.auto_download is True

    def test_portfolio_config_custom(self):
        """Test PortfolioConfig with custom values."""
        from quantrex_core import PortfolioConfig, PositionSizer
        from quantrex_core.models import PortfolioState

        class TestSizer:
            def compute_target_weights(self, portfolio, signals):
                return {}

        sizer = TestSizer()
        config = PortfolioConfig(
            initial_cash=500000.0,
            margin_requirement=2.0,
            position_sizer=sizer,
            data_start="2026-01-01",
            data_end="2026-12-31",
            auto_download=False,
        )

        assert config.initial_cash == 500000.0
        assert config.margin_requirement == 2.0
        assert config.position_sizer == sizer
        assert config.data_start == "2026-01-01"
        assert config.data_end == "2026-12-31"
        assert config.auto_download is False


class TestPortfolioContext:
    """Tests for PortfolioContext ABC and EmptyPortfolioContext."""

    def test_empty_portfolio_context(self):
        """Test EmptyPortfolioContext default values."""
        from quantrex_core.portfolio import EmptyPortfolioContext

        ctx = EmptyPortfolioContext()

        assert ctx.cash == 0.0
        assert ctx.equity == 0.0
        assert ctx.margin_used == 0.0
        assert ctx.margin_available == 0.0
        assert ctx.positions == {}
        assert ctx.unrealized_pnl == 0.0
        assert ctx.realized_pnl == 0.0

    def test_empty_portfolio_context_get_position(self):
        """Test EmptyPortfolioContext.get_position returns zero position."""
        from quantrex_core.portfolio import EmptyPortfolioContext
        from quantrex_core.models.position import Position

        ctx = EmptyPortfolioContext()
        pos = ctx.get_position("RELIANCE")

        assert isinstance(pos, Position)
        assert pos.quantity == 0.0
        assert pos.symbol == "RELIANCE"

    def test_portfolio_context_abstract(self):
        """Test that PortfolioContext cannot be instantiated directly."""
        from quantrex_core.portfolio import PortfolioContext

        try:
            PortfolioContext()
            assert False, "Should have raised TypeError"
        except TypeError:
            pass  # Expected