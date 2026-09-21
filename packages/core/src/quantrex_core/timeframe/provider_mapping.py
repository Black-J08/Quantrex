"""Provider timeframe mapping for Quantrex framework.

Defines the interface and implementations for mapping Quantrex standard timeframes
to provider-specific interval formats.
"""

from abc import ABC, abstractmethod
from typing import Optional

from quantrex_core.timeframe.parser import validate_interval


class ProviderTimeframeMapper(ABC):
    """Abstract base class for provider-specific timeframe mappers.

    Each data provider implements this to map Quantrex standard intervals
    (e.g., "1H", "1D") to their native API format (e.g., "60minute", "day").
    """

    @abstractmethod
    def to_provider(self, quantrex_interval: str) -> str:
        """Convert Quantrex interval to provider-specific format.

        Args:
            quantrex_interval: Interval in Quantrex format (e.g., "1H").

        Returns:
            Interval in provider's native format.

        Raises:
            ValueError: If interval is not supported by this provider.
        """
        pass

    @abstractmethod
    def from_provider(self, provider_interval: str) -> str:
        """Convert provider-specific interval to Quantrex format.

        Args:
            provider_interval: Interval in provider's native format.

        Returns:
            Interval in Quantrex standard format.

        Raises:
            ValueError: If provider interval is not recognized.
        """
        pass

    @abstractmethod
    def get_supported_quantrex_intervals(self) -> list[str]:
        """Get list of Quantrex intervals supported by this provider.

        Returns:
            List of Quantrex interval strings this provider can handle.
        """
        pass

    def validate_quantrex_interval(self, interval: str) -> bool:
        """Validate that an interval is a valid Quantrex format and supported.

        Args:
            interval: Interval string to validate.

        Returns:
            True if valid and supported, False otherwise.
        """
        if not validate_interval(interval):
            return False
        return interval in self.get_supported_quantrex_intervals()


class ZerodhaTimeframeMapper(ProviderTimeframeMapper):
    """Timeframe mapper for Zerodha/Kite Connect API.

    Maps Quantrex intervals to Zerodha's interval format.
    """

    # Quantrex -> Zerodha mapping
    _QUANTREX_TO_ZERODHA = {
        "1M": "minute",
        "3M": "3minute",
        "5M": "5minute",
        "10M": "10minute",
        "15M": "15minute",
        "30M": "30minute",
        "1H": "60minute",
        "1D": "day",
    }

    # Zerodha -> Quantrex mapping (reverse)
    _ZERODHA_TO_QUANTREX = {v: k for k, v in _QUANTREX_TO_ZERODHA.items()}

    # Backward compatibility: accept Zerodha native formats as input
    _BACKWARD_COMPAT = {
        "minute": "minute",
        "3minute": "3minute",
        "5minute": "5minute",
        "10minute": "10minute",
        "15minute": "15minute",
        "30minute": "30minute",
        "60minute": "60minute",
        "day": "day",
    }

    def to_provider(self, quantrex_interval: str) -> str:
        """Convert Quantrex interval to Zerodha format."""
        # First check if it's already a Zerodha native format (backward compat)
        if quantrex_interval in self._BACKWARD_COMPAT:
            return self._BACKWARD_COMPAT[quantrex_interval]

        # Otherwise map from Quantrex standard
        if quantrex_interval not in self._QUANTREX_TO_ZERODHA:
            supported = list(self._QUANTREX_TO_ZERODHA.keys())
            raise ValueError(
                f"Unsupported timeframe for Zerodha: {quantrex_interval!r}. "
                f"Supported Quantrex intervals: {supported}"
            )
        return self._QUANTREX_TO_ZERODHA[quantrex_interval]

    def from_provider(self, provider_interval: str) -> str:
        """Convert Zerodha interval to Quantrex format."""
        if provider_interval not in self._ZERODHA_TO_QUANTREX:
            supported = list(self._ZERODHA_TO_QUANTREX.keys())
            raise ValueError(
                f"Unrecognized Zerodha interval: {provider_interval!r}. "
                f"Supported: {supported}"
            )
        return self._ZERODHA_TO_QUANTREX[provider_interval]

    def get_supported_quantrex_intervals(self) -> list[str]:
        """Get Quantrex intervals supported by Zerodha."""
        return list(self._QUANTREX_TO_ZERODHA.keys())


class DhanTimeframeMapper(ProviderTimeframeMapper):
    """Timeframe mapper for Dhan API.

    Maps Quantrex intervals to Dhan's interval format.
    """

    # Quantrex -> Dhan mapping
    _QUANTREX_TO_DHAN = {
        "1M": "1",
        "5M": "5",
        "15M": "15",
        "30M": "30",
        "1H": "60",
        "1D": "D",
    }

    # Dhan -> Quantrex mapping (reverse)
    _DHAN_TO_QUANTREX = {v: k for k, v in _QUANTREX_TO_DHAN.items()}

    def to_provider(self, quantrex_interval: str) -> str:
        """Convert Quantrex interval to Dhan format."""
        if quantrex_interval not in self._QUANTREX_TO_DHAN:
            supported = list(self._QUANTREX_TO_DHAN.keys())
            raise ValueError(
                f"Unsupported timeframe for Dhan: {quantrex_interval!r}. "
                f"Supported Quantrex intervals: {supported}"
            )
        return self._QUANTREX_TO_DHAN[quantrex_interval]

    def from_provider(self, provider_interval: str) -> str:
        """Convert Dhan interval to Quantrex format."""
        if provider_interval not in self._DHAN_TO_QUANTREX:
            supported = list(self._DHAN_TO_QUANTREX.keys())
            raise ValueError(
                f"Unrecognized Dhan interval: {provider_interval!r}. "
                f"Supported: {supported}"
            )
        return self._DHAN_TO_QUANTREX[provider_interval]

    def get_supported_quantrex_intervals(self) -> list[str]:
        """Get Quantrex intervals supported by Dhan."""
        return list(self._QUANTREX_TO_DHAN.keys())


# Default mapper instances for convenience
ZERODHA_MAPPER = ZerodhaTimeframeMapper()
DHAN_MAPPER = DhanTimeframeMapper()


def get_mapper(provider_name: str) -> ProviderTimeframeMapper:
    """Get a provider timeframe mapper by name.

    Args:
        provider_name: Name of the provider ("zerodha", "dhan").

    Returns:
        ProviderTimeframeMapper instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    mappers = {
        "zerodha": ZERODHA_MAPPER,
        "dhan": DHAN_MAPPER,
    }
    if provider_name.lower() not in mappers:
        raise ValueError(
            f"Unknown provider: {provider_name!r}. "
            f"Supported: {list(mappers.keys())}"
        )
    return mappers[provider_name.lower()]