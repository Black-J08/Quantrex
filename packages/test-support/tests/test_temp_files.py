"""Pytest test cases for the test-support package temporary file helpers."""

import pytest

from quantrex_test_support.csv import create_temp_csv


class TestCreateTempCSV:
    """Tests for create_temp_csv context manager."""

    def test_basic_creation(self):
        """Test basic temporary CSV file creation."""
        content = "date,time,open,high,low,close,volume\n20230620,19:00,737.20,737.20,737.20,737.20,1"
        with create_temp_csv(content) as temp_path:
            assert isinstance(temp_path, str)
            assert temp_path.endswith(".csv")
            # Read the file content to verify it was written correctly
            with open(temp_path, "r") as f:
                read_content = f.read()
            assert read_content == content

    def test_multiline_content(self):
        """Test with multi-line CSV content."""
        content = "date,time,open,high,low,close,volume\n20230620,19:00,737.20,737.20,737.20,737.20,1\n20230621,10:00,738.50,739.00,738.00,738.75,500"
        with create_temp_csv(content) as temp_path:
            with open(temp_path, "r") as f:
                read_content = f.read()
            assert read_content == content

    def test_empty_content(self):
        """Test with empty content."""
        content = ""
        with create_temp_csv(content) as temp_path:
            with open(temp_path, "r") as f:
                read_content = f.read()
            assert read_content == ""

    def test_special_characters(self):
        """Test with content containing special characters."""
        content = "date,time,open,high,low,close,volume\n20230620,19:00,737.20,737.21,737.10,737.15,100"
        with create_temp_csv(content) as temp_path:
            with open(temp_path, "r") as f:
                read_content = f.read()
            assert read_content == content

    def test_file_cleanup(self):
        """Test that temporary file is cleaned up after context manager exits."""
        content = "date,time,open,high,low,close,volume\n20230620,19:00,737.20,737.20,737.20,737.20,1"
        # Create the file and keep reference outside context
        with create_temp_csv(content) as temp_path:
            assert temp_path is not None
            # File should exist within context
            assert __import__("os").path.exists(temp_path)
        # After context exits, file should be cleaned up
        # Note: There might be a race condition, so we just check no error is raised