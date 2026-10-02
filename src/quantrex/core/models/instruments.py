"""Instrument definitions for the trading framework."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class AssetClass(Enum):
    """Asset class enumeration."""

    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"

class ContractType(Enum):
    """Contract type enumeration."""

    FUTURE = "FUTURE"
    OPTION = "OPTION"
    
class OptionType(Enum):
    """Option type enumeration."""

    CALL = "CALL"
    PUT = "PUT"

@dataclass(slots=True, kw_only=True, frozen=True)
class ContractSpec:
    """Contract specification for derivatives.

    Attributes:
        contract_type: Type of the contract (FUTURE or OPTION).
        expiration: Expiration date for futures/options.
        option_type: Type of the option (CALL/PUT) for options.
        strike: Strike price for options.
    """

    contract_type: ContractType
    expiration: str | None = None
    option_type: OptionType | None = None
    strike: Decimal | None = None


    def __post_init__(self) -> None:
        """Validate contract spec fields."""
        if not self.expiration:
            raise ValueError("expiration is required for ContractSpec")
        if self.contract_type == ContractType.OPTION:
            if self.option_type is None:
                raise ValueError("option_type is required for OPTION contracts")
            if self.strike is None:
                raise ValueError("strike is required for OPTION contracts")
        if self.contract_type == ContractType.FUTURE:
            if self.option_type is not None:
                raise ValueError("option_type must be None for FUTURE contracts")
            if self.strike is not None:
                raise ValueError("strike must be None for FUTURE contracts")

@dataclass(slots=True, kw_only=True, frozen=True)
class InstrumentSpec:
    """Tradable instrument definition.

    Attributes:
        symbol: Unique symbol identifier (e.g., "AAPL", "ESU24").
        asset_class: Asset class of the instrument.
        exchange: Exchange where the instrument is traded.
        contract_spec: Contract specification for derivatives (optional).
    """

    symbol: str
    asset_class: AssetClass
    exchange: str
    contract_spec: ContractSpec | None = None

    def __post_init__(self) -> None:
        """Validate and initialize instrument fields."""
        if not self.symbol:
            raise ValueError("InstrumentSpec.symbol cannot be empty")
        if not self.exchange:
            raise ValueError("InstrumentSpec.exchange cannot be empty")
        if not self.asset_class:
            raise ValueError("InstrumentSpec.asset_class cannot be empty")
        if (self.asset_class != AssetClass.EQUITY) and (self.contract_spec is None):
            raise ValueError(f"InstrumentSpec.ContractSpec cannot be empty with asset_class:{self.asset_class}")