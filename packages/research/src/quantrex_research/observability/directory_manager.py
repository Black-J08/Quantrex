"""Run directory management for Quantrex Research."""

from datetime import datetime
from pathlib import Path

from quantrex_core.logging import get_logger

logger = get_logger(__name__)


def _format_timestamp_local(dt: datetime) -> str:
    """Format datetime as YYYYMMDD_HHMMSS (local timezone, with seconds)."""
    return dt.strftime("%Y%m%d_%H%M%S")


class ResearchDirectoryManager:
    """Manages run directory lifecycle for research execution.

    Handles run directory creation with timestamp-based naming.
    """

    def build_run_dir(
        self,
        component_name: str,
        run_start_local: datetime | None = None,
    ) -> Path:
        """Build the per-run output directory path (does not create it).

        Format: output/research/{ComponentName}/{timestamp}/
        Example: output/research/HourlyInsideBreakoutResearch/20260926_053557/
        """
        if run_start_local is None:
            run_start_local = datetime.now()

        timestamp_str = _format_timestamp_local(run_start_local)

        return (
            Path("output")
            / "research"
            / component_name
            / timestamp_str
        )