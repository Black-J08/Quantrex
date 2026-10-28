"""Shared timezone facts for Quantrex.

Timezone constants that are used across multiple modules (broker, data,
normalization) live here so that no single module owns a cross-cutting
timezone concern.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

#: Indian market timezone. Zerodha returns timestamps with a +05:30 offset
#: and reads request bounds as IST wall-clock values.
IST = ZoneInfo("Asia/Kolkata")
