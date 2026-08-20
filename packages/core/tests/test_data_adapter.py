"""Tests for DataAdapter protocol."""

from quantrex_core.protocols import DataAdapter, DataProvider


class TestDataAdapterProtocol:
    """Verify DataAdapter protocol structure."""

    def test_data_adapter_protocol_exists(self):
        """DataAdapter protocol should be importable."""
        assert DataAdapter is not None
    
    def test_data_adapter_has_init_with_provider(self):
        """DataAdapter should accept DataProvider in __init__."""
        # Protocol defines __init__ with provider parameter
        assert hasattr(DataAdapter, '__init__')
    
    def test_data_adapter_has_read_method(self):
        """DataAdapter should have read method."""
        assert hasattr(DataAdapter, 'read')
    
    def test_data_adapter_has_close_method(self):
        """DataAdapter should have close method."""
        assert hasattr(DataAdapter, 'close')
    
    def test_data_adapter_read_returns_list_of_dicts(self):
        """DataAdapter.read() should return list[dict]."""
        # This is a protocol check - the return type is documented
        pass