"""Run directory management for Quantrex Backtest."""

from datetime import datetime
from pathlib import Path

from quantrex_core.logging import get_logger

logger = get_logger(__name__)

_RUN_LOG_FILENAME = "execution.log"
_EXECUTION_LOG_DIR = "execution_log"


def _format_timestamp_local(dt: datetime) -> str:
    """Format datetime as YYYYMMDD_HHMM (local timezone, no seconds)."""
    return dt.strftime("%Y%m%d_%H%M")


def _format_date_ddmmyy(dt: datetime) -> str:
    """Format datetime as DDMonYY (e.g., 01Jan26)."""
    return dt.strftime("%d%b%y").capitalize()


class RunDirectoryManager:
    """Manages run directory lifecycle for backtest execution.

    Handles staging directory creation, final directory promotion,
    and log file management.
    """

    def build_run_dir(
        self,
        backtest_start_local: datetime,
        data_start: datetime | None,
        data_end: datetime | None,
        strategy_name: str,
    ) -> Path:
        """Build the per-run output directory path (does not create it).

        Format: output/backtest/{StrategyName}/{timestamp}*{start_date}*{end_date}/
        Example: output/backtest/TestStrategy/20260920_0135*01Jan26_31Jan26/
        """
        timestamp_str = _format_timestamp_local(backtest_start_local)

        if data_start is None or data_end is None:
            # Use backtest start time as fallback
            start_date_str = _format_date_ddmmyy(backtest_start_local)
            end_date_str = _format_date_ddmmyy(backtest_start_local)
        else:
            start_date_str = _format_date_ddmmyy(data_start)
            end_date_str = _format_date_ddmmyy(data_end)

        return (
            Path("output")
            / "backtest"
            / strategy_name
            / f"{timestamp_str}*{start_date_str}*{end_date_str}"
        )

    def promote_staging_to_final(
        self,
        staging_dir: Path,
        final_run_dir: Path,
        symbols: list[str],
        run_logger,
    ) -> Path:
        """Move a staging run directory's files into the final location.

        Used when the data window only becomes known after the first
        candle is processed. Creates ``final_run_dir`` if it doesn't exist
        and moves ``closed_trades.csv`` + ``execution_log/`` into it, then
        reattaches the per-run log handler so subsequent log calls land
        in the new path. Removes the (now-empty) staging directory and
        returns the final directory.
        """
        final_run_dir.mkdir(parents=True, exist_ok=True)

        # Move closed_trades.csv
        src_csv = staging_dir / "closed_trades.csv"
        if src_csv.exists():
            src_csv.rename(final_run_dir / "closed_trades.csv")

        # Move execution_log directory
        src_exec_log = staging_dir / _EXECUTION_LOG_DIR
        if src_exec_log.exists():
            dst_exec_log = final_run_dir / _EXECUTION_LOG_DIR
            if dst_exec_log.exists():
                # Merge contents if destination exists
                for log_file in src_exec_log.iterdir():
                    if log_file.is_file():
                        log_file.rename(dst_exec_log / log_file.name)
                src_exec_log.rmdir()
            else:
                src_exec_log.rename(dst_exec_log)

        # Remove the empty staging directory so it doesn't pollute
        # "latest output dir" tests.
        try:
            staging_dir.rmdir()
        except OSError:
            # Staging dir wasn't empty (e.g. external process wrote into
            # it); leave it in place rather than masking the cause.
            pass

        # Rebind the handler to the new log path.
        run_logger.rebind_log_handlers(final_run_dir / _EXECUTION_LOG_DIR, symbols)
        return final_run_dir