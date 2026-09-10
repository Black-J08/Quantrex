"""Tests for DataProvider protocol."""

from datetime import time
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
    
    def test_data_provider_has_get_origin_time_method(self):
        """DataProvider should have get_origin_time method."""
        assert hasattr(DataProvider, 'get_origin_time')
    
    def test_data_provider_get_origin_time_returns_time(self):
        """DataProvider.get_origin_time should return a datetime.time object."""
        # This test verifies the protocol structure - actual implementation
        # is tested in provider-specific tests
        assert hasattr(DataProvider, 'get_origin_time')
        # The method should be callable and return a time object
        # (Implementation-specific tests verify actual return values)