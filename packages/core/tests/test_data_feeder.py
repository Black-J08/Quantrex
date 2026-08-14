"""Tests for DataFeeder protocol."""

from quantrex_core import DataFeeder


def test_data_feeder_is_protocol():
    """DataFeeder is a Protocol class."""
    # Protocol classes cannot be instantiated directly
    # but we can verify it's a Protocol
    assert hasattr(DataFeeder, '__protocol_attrs__')


def test_data_feeder_requires_read_method():
    """DataFeeder protocol requires a read method."""
    # Check that read is in the protocol attributes
    assert 'read' in DataFeeder.__protocol_attrs__


def test_csv_reader_satisfies_protocol():
    """CSVReader from quantrex-data satisfies DataFeeder protocol."""
    from quantrex_data.providers.csv_reader import CSVReader
    
    # CSVReader should satisfy the DataFeeder protocol via duck typing
    # We can't easily test this without a CSV file, but we can verify
    # the class has the required method
    assert hasattr(CSVReader, 'read')
    assert callable(getattr(CSVReader, 'read'))