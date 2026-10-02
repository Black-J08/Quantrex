"""Tests for instrument models."""

from __future__ import annotations

import pytest
from decimal import Decimal

from quantrex.core.models import (
    AssetClass,
    ContractType,
    OptionType,
    ContractSpec,
    InstrumentSpec,
)


class TestAssetClass:
    """Tests for AssetClass enum."""

    def test_values(self) -> None:
        assert AssetClass.EQUITY.value == "EQUITY"
        assert AssetClass.FUTURE.value == "FUTURE"
        assert AssetClass.OPTION.value == "OPTION"


class TestContractType:
    """Tests for ContractType enum."""

    def test_values(self) -> None:
        assert ContractType.FUTURE.value == "FUTURE"
        assert ContractType.OPTION.value == "OPTION"


class TestOptionType:
    """Tests for OptionType enum."""

    def test_values(self) -> None:
        assert OptionType.CALL.value == "CALL"
        assert OptionType.PUT.value == "PUT"


class TestContractSpec:
    """Tests for ContractSpec."""

    def test_future_creation(self) -> None:
        """Test creating a future contract spec."""
        spec = ContractSpec(
            contract_type=ContractType.FUTURE,
            expiration="2024-12-26",
        )
        assert spec.contract_type == ContractType.FUTURE
        assert spec.expiration == "2024-12-26"
        assert spec.option_type is None
        assert spec.strike is None

    def test_option_creation(self) -> None:
        """Test creating an option contract spec."""
        spec = ContractSpec(
            contract_type=ContractType.OPTION,
            expiration="2024-12-26",
            option_type=OptionType.CALL,
            strike=Decimal("24000"),
        )
        assert spec.contract_type == ContractType.OPTION
        assert spec.option_type == OptionType.CALL
        assert spec.strike == Decimal("24000")

    def test_future_with_option_type_raises(self) -> None:
        """Test that future with option_type raises."""
        with pytest.raises(ValueError, match="option_type must be None"):
            ContractSpec(
                contract_type=ContractType.FUTURE,
                expiration="2024-12-26",
                option_type=OptionType.CALL,
            )

    def test_future_with_strike_raises(self) -> None:
        """Test that future with strike raises."""
        with pytest.raises(ValueError, match="strike must be None"):
            ContractSpec(
                contract_type=ContractType.FUTURE,
                expiration="2024-12-26",
                strike=Decimal("24000"),
            )

    def test_option_without_option_type_raises(self) -> None:
        """Test that option without option_type raises."""
        with pytest.raises(ValueError, match="option_type is required"):
            ContractSpec(
                contract_type=ContractType.OPTION,
                expiration="2024-12-26",
                strike=Decimal("24000"),
            )

    def test_option_without_strike_raises(self) -> None:
        """Test that option without strike raises."""
        with pytest.raises(ValueError, match="strike is required"):
            ContractSpec(
                contract_type=ContractType.OPTION,
                expiration="2024-12-26",
                option_type=OptionType.CALL,
            )

    def test_missing_expiration_raises(self) -> None:
        """Test that missing expiration raises."""
        with pytest.raises(ValueError, match="expiration is required"):
            ContractSpec(contract_type=ContractType.FUTURE)

    def test_immutability(self) -> None:
        """Test that ContractSpec is frozen."""
        spec = ContractSpec(contract_type=ContractType.FUTURE, expiration="2024-12-26")
        with pytest.raises(Exception):
            spec.expiration = "2025-01-01"


class TestInstrumentSpec:
    """Tests for InstrumentSpec."""

    def test_equity_creation(self) -> None:
        """Test creating an equity instrument."""
        inst = InstrumentSpec(
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            exchange="NASDAQ",
        )
        assert inst.symbol == "AAPL"
        assert inst.asset_class == AssetClass.EQUITY
        assert inst.exchange == "NASDAQ"
        assert inst.contract_spec is None

    def test_future_creation(self) -> None:
        """Test creating a future instrument."""
        spec = ContractSpec(contract_type=ContractType.FUTURE, expiration="2024-12-26")
        inst = InstrumentSpec(
            symbol="NIFTY24DECFUT",
            asset_class=AssetClass.FUTURE,
            exchange="NSE",
            contract_spec=spec,
        )
        assert inst.asset_class == AssetClass.FUTURE
        assert inst.contract_spec == spec

    def test_option_creation(self) -> None:
        """Test creating an option instrument."""
        spec = ContractSpec(
            contract_type=ContractType.OPTION,
            expiration="2024-12-26",
            option_type=OptionType.CALL,
            strike=Decimal("24000"),
        )
        inst = InstrumentSpec(
            symbol="NIFTY24DEC24000CE",
            asset_class=AssetClass.OPTION,
            exchange="NSE",
            contract_spec=spec,
        )
        assert inst.asset_class == AssetClass.OPTION
        assert inst.contract_spec == spec

    def test_empty_symbol_raises(self) -> None:
        """Test that empty symbol raises."""
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            InstrumentSpec(symbol="", asset_class=AssetClass.EQUITY, exchange="NASDAQ")

    def test_empty_exchange_raises(self) -> None:
        """Test that empty exchange raises."""
        with pytest.raises(ValueError, match="exchange cannot be empty"):
            InstrumentSpec(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="")

    def test_empty_asset_class_raises(self) -> None:
        """Test that empty asset_class raises."""
        with pytest.raises(ValueError, match="asset_class cannot be empty"):
            InstrumentSpec(symbol="AAPL", asset_class=None, exchange="NASDAQ")  # type: ignore[arg-type]

    def test_non_equity_without_contract_spec_raises(self) -> None:
        """Test that non-equity without contract_spec raises."""
        with pytest.raises(ValueError, match="ContractSpec cannot be empty"):
            InstrumentSpec(symbol="NIFTY", asset_class=AssetClass.FUTURE, exchange="NSE")

    def test_immutability(self) -> None:
        """Test that InstrumentSpec is frozen."""
        inst = InstrumentSpec(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")
        with pytest.raises(Exception):
            inst.symbol = "GOOGL"