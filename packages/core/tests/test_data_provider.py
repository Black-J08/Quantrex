"""Tests for DataProvider protocol."""

from quantrex_core.protocols import DataProvider


class TestDataProviderProtocol:
    """Verify DataProvider protocol structure."""

    def test_data_provider_protocol_exists(self):
        """DataProvider protocol should be importable."""
        assert DataProvider is not None
    
    def test_data_provider_has_fetch_method(self):
        """DataProvider should have fetch method."""
        assert hasattr(DataProvider, 'fetch')
    
    def test_data_provider_has_close_method(self):
        """DataProvider should have close method."""
        assert hasattr(DataProvider, 'close')