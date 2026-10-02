"""Base event classes for the event-driven trading framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class Event:
    """Base event class for all events in the system.

    Attributes:
        event_id: Unique identifier for this event.
        timestamp: Timestamp when the event occurred (timezone-aware, system local timezone).
    """

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now().astimezone()
    )

    def __post_init__(self) -> None:
        """Validate timestamp is timezone-aware."""
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    def __eq__(self, other: object) -> bool:
        """Compare events by event_id only."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        """Hash based on event_id for use in sets/dicts."""
        return hash(self.event_id)