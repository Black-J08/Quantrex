#!/usr/bin/env python3
"""
Convert Quantrex closed_trades.csv to the target format.

Input format:
symbol,side,quantity,entry_timestamp,entry_price,exit_timestamp,exit_price,pnl

Output format:
Key,ExitTime,Symbol,EntryPrice,ExitPrice,Quantity,PositionStatus,Pnl,ExitType
"""

import csv
import sys
from pathlib import Path
from datetime import datetime


def convert_trades(input_path: Path, output_path: Path) -> None:
    """Convert trades CSV to target format."""
    with input_path.open("r", newline="") as infile, output_path.open("w", newline="") as outfile:
        reader = csv.DictReader(infile)
        writer = csv.writer(outfile)

        # Write header
        writer.writerow([
            "Key", "ExitTime", "Symbol", "EntryPrice", "ExitPrice",
            "Quantity", "PositionStatus", "Pnl", "ExitType"
        ])

        for row in reader:
            # Parse timestamps
            entry_ts = datetime.fromisoformat(row["entry_timestamp"])
            exit_ts = datetime.fromisoformat(row["exit_timestamp"])

            # Map side to PositionStatus: LONG=1, SHORT=-1
            position_status = 1 if row["side"] == "LONG" else -1

            # Default ExitType
            exit_type = "EOD"

            writer.writerow([
                entry_ts.strftime("%Y-%m-%d %H:%M:%S"),
                exit_ts.strftime("%Y-%m-%d %H:%M:%S"),
                row["symbol"],
                row["entry_price"],
                row["exit_price"],
                row["quantity"],
                position_status,
                row["pnl"],
                exit_type
            ])


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python convert_trades.py <input_csv> [output_csv]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_name("converted_trades.csv")

    convert_trades(input_path, output_path)
    print(f"Converted {input_path} -> {output_path}")


if __name__ == "__main__":
    main()