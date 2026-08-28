"""Tests for Dhan instrument master CSV parsing.

These tests pin the parser to the actual upstream schema published by Dhan at
https://images.dhan.co/api-data/api-scrip-master.csv. The most important
regression test is `test_parses_live_dhan_schema` which uses the canonical
column names; this is the failure mode that caused every symbol lookup to
silently return an empty dict, surfacing as ``DhanSymbolNotFoundError``.
"""

import pytest

from quantrex_data.providers.dhan_provider.config import DhanProviderConfig
from quantrex_data.providers.dhan_provider.exceptions import (
    DhanInstrumentMasterError,
    DhanSymbolNotFoundError,
)
from quantrex_data.providers.dhan_provider.instrument_master import (
    InstrumentMaster,
)
from quantrex_test_support.dhan import MOCK_INSTRUMENT_MASTER_CSV


def _make_master(tmp_path) -> InstrumentMaster:
    """Build an InstrumentMaster with a private, non-existent cache dir."""
    config = DhanProviderConfig(
        security_id="1333",  # bypass the symbol-required check
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        from_date="2024-01-01",
        to_date="2024-01-31",
        cache_dir=tmp_path,
        cache_ttl_hours=1,
    )
    return InstrumentMaster(config)


def test_parses_live_dhan_schema(tmp_path):
    """Regression: the parser must use Dhan's actual SEM_* column names.

    Before the fix, the parser looked up ``EXCH_ID``/``SEGMENT``/``SECURITY_ID``
    and produced an empty dict, so every symbol resolution raised
    ``DhanSymbolNotFoundError`` instead of reporting a schema mismatch.
    """
    master = _make_master(tmp_path)

    lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)

    # NSE equity rows from the live-style fixture.
    assert lookup[("NSE_EQ", "RELIANCE")] == "1333"
    assert lookup[("NSE_EQ", "TCS")] == "11536"
    assert lookup[("NSE_EQ", "HDFCBANK")] == "2885"
    # BSE equity - same symbol, different exchange segment.
    assert lookup[("BSE_EQ", "RELIANCE")] == "500325"
    # MCX commodity future.
    assert lookup[("MCX_COMM", "COPPER24JANFUT")] == "12345"
    # NSE FNO future/option.
    assert lookup[("NSE_FNO", "RELIANCE24JANFUT")] == "1333"
    assert lookup[("NSE_FNO", "RELIANCE24JAN2500CE")] == "1333"


def test_resolve_symbol_returns_security_id(tmp_path):
    """End-to-end: resolve_symbol must work without touching the network."""
    master = _make_master(tmp_path)
    master._lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)
    master._loaded = True

    assert master.resolve_symbol("RELIANCE", "NSE_EQ") == "1333"
    assert master.resolve_symbol("RELIANCE", "BSE_EQ") == "500325"


def test_resolve_symbol_missing_raises_clear_error(tmp_path):
    """Unknown symbols must raise DhanSymbolNotFoundError, not silently return None."""
    master = _make_master(tmp_path)
    master._lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)
    master._loaded = True

    with pytest.raises(DhanSymbolNotFoundError) as exc:
        master.resolve_symbol("DOES_NOT_EXIST", "NSE_EQ")

    assert exc.value.symbol == "DOES_NOT_EXIST"
    assert exc.value.exchange_segment == "NSE_EQ"


def test_missing_required_column_raises_instrument_master_error(tmp_path):
    """If a future schema change drops a required column, fail loudly."""
    # Build a CSV whose header lacks SEM_SMST_SECURITY_ID.
    bad_csv = (
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_INSTRUMENT_NAME,SEM_TRADING_SYMBOL\n"
        "NSE,E,EQUITY,RELIANCE\n"
    )

    master = _make_master(tmp_path)

    with pytest.raises(DhanInstrumentMasterError) as exc:
        master._parse_csv(bad_csv)

    assert "security_id" in str(exc.value)
    assert "SEM_SMST_SECURITY_ID" in str(exc.value)


def test_empty_parsed_lookup_raises_instrument_master_error(tmp_path):
    """A schema that parses headers but yields zero usable rows must error.

    This catches silent regressions where headers look right but every data
    row is skipped (e.g. all required fields blank).
    """
    # Valid headers, but every required cell is empty.
    bad_csv = (
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_TRADING_SYMBOL\n"
        ",,,,,,,\n"
    )

    master = _make_master(tmp_path)

    with pytest.raises(DhanInstrumentMasterError) as exc:
        master._parse_csv(bad_csv)

    assert "0 usable rows" in str(exc.value)


def test_legacy_alias_columns_still_supported(tmp_path):
    """Older column names (EXCH_ID, SEGMENT, SECURITY_ID) must still work.

    The alias map lets the parser survive upstream renames without code
    changes, as long as at least one alias per logical key is present.
    """
    legacy_csv = (
        "EXCH_ID,SEGMENT,SECURITY_ID,SEM_TRADING_SYMBOL\n"
        "NSE,E,1333,RELIANCE\n"
        "BSE,E,500325,RELIANCE\n"
    )

    master = _make_master(tmp_path)
    lookup = master._parse_csv(legacy_csv)

    assert lookup[("NSE_EQ", "RELIANCE")] == "1333"
    assert lookup[("BSE_EQ", "RELIANCE")] == "500325"
