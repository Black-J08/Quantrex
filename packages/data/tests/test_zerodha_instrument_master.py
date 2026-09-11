"""Tests for Zerodha instrument master CSV parsing.

These tests pin the parser to the actual upstream schema published by Zerodha at
https://api.kite.trade/instruments. The most important
regression test is `test_parses_live_zerodha_schema` which uses the canonical
column names; this is the failure mode that caused every symbol lookup to
silently return an empty dict, surfacing as ``ZerodhaSymbolNotFoundError``.
"""

import pytest

from quantrex_data.providers.zerodha_provider.config import ZerodhaProviderConfig
from quantrex_data.providers.zerodha_provider.exceptions import (
    ZerodhaInstrumentMasterError,
    ZerodhaSymbolNotFoundError,
)
from quantrex_data.providers.zerodha_provider.instrument_master import (
    InstrumentMaster,
)
from quantrex_test_support.zerodha import MOCK_INSTRUMENT_MASTER_CSV


def _make_master(tmp_path) -> InstrumentMaster:
    """Build an InstrumentMaster with a private, non-existent cache dir."""
    config = ZerodhaProviderConfig(
        api_key="test_key",
        api_secret="test_secret",
        access_token="test_token",
        instrument_token="5633",  # bypass the symbol-required check
        exchange="NSE",
        from_date="2024-01-01",
        to_date="2024-01-31",
        cache_dir=tmp_path,
        cache_ttl_hours=1,
    )
    return InstrumentMaster(config)


def test_parses_live_zerodha_schema(tmp_path):
    """Regression: the parser must use Zerodha's actual column names.

    Before the fix, the parser looked up wrong column names
    and produced an empty dict, so every symbol resolution raised
    ``ZerodhaSymbolNotFoundError`` instead of reporting a schema mismatch.
    """
    master = _make_master(tmp_path)

    lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)

    # NSE equity rows from the live-style fixture.
    assert lookup[("NSE", "INFY")] == "408065"
    assert lookup[("NSE", "RELIANCE")] == "5633"
    # NFO future/option.
    assert lookup[("NFO", "NIFTY24JANFUT")] == "5720322"
    assert lookup[("NFO", "NIFTY24JAN25000CE")] == "5720578"
    assert lookup[("NFO", "NIFTY24JAN25000PE")] == "5720579"
    # MCX commodity future.
    assert lookup[("MCX", "COPPER24JANFUT")] == "12345"


def test_resolve_symbol_returns_instrument_token(tmp_path):
    """End-to-end: resolve_symbol must work without touching the network."""
    master = _make_master(tmp_path)
    master._lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)
    master._loaded = True

    assert master.resolve_symbol("INFY", "NSE") == "408065"
    assert master.resolve_symbol("RELIANCE", "NSE") == "5633"


def test_resolve_symbol_missing_raises_clear_error(tmp_path):
    """Unknown symbols must raise ZerodhaSymbolNotFoundError, not silently return None."""
    master = _make_master(tmp_path)
    master._lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)
    master._loaded = True

    with pytest.raises(ZerodhaSymbolNotFoundError) as exc:
        master.resolve_symbol("DOES_NOT_EXIST", "NSE")

    assert exc.value.symbol == "DOES_NOT_EXIST"
    assert exc.value.exchange == "NSE"


def test_missing_required_column_raises_instrument_master_error(tmp_path):
    """If a future schema change drops a required column, fail loudly."""
    # Build a CSV whose header lacks instrument_token.
    bad_csv = (
        "exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange\n"
        "1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE\n"
    )

    master = _make_master(tmp_path)

    with pytest.raises(ZerodhaInstrumentMasterError) as exc:
        master._parse_csv(bad_csv)

    assert "instrument_token" in str(exc.value)


def test_case_insensitive_symbol_lookup(tmp_path):
    """Symbol lookup should be case-insensitive as a fallback."""
    master = _make_master(tmp_path)
    master._lookup = master._parse_csv(MOCK_INSTRUMENT_MASTER_CSV)
    master._loaded = True

    # Test case-insensitive fallback
    assert master.resolve_symbol("infy", "NSE") == "408065"
    assert master.resolve_symbol("reliance", "nse") == "5633"