"""Tests for base models."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from quantrex.core.models import Event


class TestEvent:
    """Tests for Event base class."""

    def test_default_creation(self) -> None:
        """Test Event creation with defaults."""
        event = Event()
        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.timestamp.tzinfo is not None

    def test_custom_timestamp(self) -> None:
        """Test Event creation with custom timestamp."""
        ts = datetime.now(timezone.utc)
        event = Event(timestamp=ts)
        assert event.timestamp == ts

    def test_custom_event_id(self) -> None:
        """Test Event creation with custom event_id."""
        from uuid import uuid4
        eid = uuid4()
        event = Event(event_id=eid)
        assert event.event_id == eid

    def test_naive_timestamp_raises(self) -> None:
        """Test that naive datetime raises ValueError."""
        with pytest.raises(ValueError, match="timezone-aware"):
            Event(timestamp=datetime.now())

    def test_immutability(self) -> None:
        """Test that Event is frozen/immutable."""
        event = Event()
        with pytest.raises(Exception):
            event.symbol = "TEST"  # type: ignore[attr-defined]

    def test_equality(self) -> None:
        """Test Event equality based on event_id."""
        eid = "12345678-1234-5678-1234-567812345678"
        from uuid import UUID
        event1 = Event(event_id=UUID(eid))
        event2 = Event(event_id=UUID(eid))
        event3 = Event()
        assert event1 == event2
        assert event1 != event3