"""Timezone facts for the Zerodha broker.

Zerodha (Kite) operates on Indian market time. The vendor sends candle
timestamps with a ``+05:30`` offset, interprets request bounds as IST
wall-clock times, and publishes its instrument master around 08:30 IST.
Those are vendor facts, so they live here rather than in the shared models.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

#: Indian market timezone. Zerodha returns timestamps with a +05:30 offset
#: and reads request bounds as IST wall-clock values.
IST = ZoneInfo("Asia/Kolkata")
