#!/usr/bin/env python3
"""
Profiling script for comparing mcb_example_strategy.py and intraday_breakout_strategy.py
using py-spy. Generates flame graphs and profiling data for analysis.
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Profiling output directory
PROFILING_DIR = project_root / "profiling" / "results"
PROFILING_DIR.mkdir(parents=True, exist_ok=True)

# Timestamp for this profiling run
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Strategy files to profile
STRATEGIES = {
    "mcb_example_strategy": {
        "file": "examples/mcb_example_strategy.py",
        "description": "MCB Breakout Strategy (30M timeframe, daily breakout levels)"
    },
    "intraday_breakout_strategy": {
        "file": "examples/intraday_breakout_strategy.py",
        "description": "Intraday Breakout Strategy (1H timeframe, inside candle pattern)"
    }
}

def run_py_spy_profile(strategy_name: str, strategy_file: str, duration: int = 60):
    """Run py-spy profiling on a strategy script."""
    print(f"\n{'='*60}")
    print(f"Profiling {strategy_name}")
    print(f"{'='*60}")
    
    # Output files
    flamegraph_file = PROFILING_DIR / f"{strategy_name}_{TIMESTAMP}_flamegraph.svg"
    speedscope_file = PROFILING_DIR / f"{strategy_name}_{TIMESTAMP}_speedscope.json"
    raw_file = PROFILING_DIR / f"{strategy_name}_{TIMESTAMP}_raw.txt"
    
    # Build py-spy command
    # We use 'record' mode with subprocess to profile the entire run
    python_path = "/home/black_j/Dev/Quantrex/.venv/bin/python"
    cmd = [
        "uv", "run", "py-spy", "record",
        "-o", str(flamegraph_file),
        "--format", "flamegraph",
        "--duration", str(duration),
        "--rate", "100",  # 100 samples per second
        "--native",  # Include native frames
        "--",  # Separator for the target command
        python_path, str(project_root / strategy_file)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Output: {flamegraph_file}")
    
    try:
        # Run with timeout
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 30)
        
        if result.returncode == 0:
            print(f"✓ Profiling completed successfully")
            print(f"  Flamegraph: {flamegraph_file}")
        else:
            print(f"✗ Profiling failed with return code {result.returncode}")
            print(f"  stderr: {result.stderr}")
            print(f"  stdout: {result.stdout}")
            
    except subprocess.TimeoutExpired:
        print(f"✗ Profiling timed out after {duration + 30} seconds")
    except Exception as e:
        print(f"✗ Profiling error: {e}")
    
    # Also generate speedscope format for interactive analysis
    cmd_speedscope = [
        "uv", "run", "py-spy", "record",
        "-o", str(speedscope_file),
        "--format", "speedscope",
        "--duration", str(duration),
        "--rate", "100",
        "--native",
        "--",
        python_path, str(project_root / strategy_file)
    ]
    
    print(f"Generating speedscope format...")
    try:
        result = subprocess.run(cmd_speedscope, capture_output=True, text=True, timeout=duration + 30)
        if result.returncode == 0:
            print(f"  Speedscope: {speedscope_file}")
        else:
            print(f"  Speedscope generation failed: {result.stderr}")
    except Exception as e:
        print(f"  Speedscope error: {e}")
    
    # Generate raw text output for quick analysis
    cmd_raw = [
        "uv", "run", "py-spy", "record",
        "-o", str(raw_file),
        "--format", "raw",
        "--duration", str(duration),
        "--rate", "100",
        "--native",
        "--",
        python_path, str(project_root / strategy_file)
    ]
    
    print(f"Generating raw format...")
    try:
        result = subprocess.run(cmd_raw, capture_output=True, text=True, timeout=duration + 30)
        if result.returncode == 0:
            print(f"  Raw: {raw_file}")
        else:
            print(f"  Raw generation failed: {result.stderr}")
    except Exception as e:
        print(f"  Raw error: {e}")

def run_py_spy_top(strategy_name: str, strategy_file: str, duration: int = 30):
    """Run py-spy top for quick interactive view."""
    print(f"\n{'='*60}")
    print(f"Running py-spy top for {strategy_name} (quick view)")
    print(f"{'='*60}")
    
    python_path = "/home/black_j/Dev/Quantrex/.venv/bin/python"
    cmd = [
        "uv", "run", "py-spy", "top",
        "--duration", str(duration),
        "--rate", "100",
        "--",
        python_path, str(project_root / strategy_file)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    try:
        # Run interactively - this will show live output
        subprocess.run(cmd, timeout=duration + 10)
    except subprocess.TimeoutExpired:
        print("Top view completed (timed out)")
    except KeyboardInterrupt:
        print("Top view interrupted")
    except Exception as e:
        print(f"Top view error: {e}")

def main():
    """Main profiling entry point."""
    print("Quantrex Strategy Profiling with py-spy")
    print(f"Project root: {project_root}")
    print(f"Profiling output: {PROFILING_DIR}")
    print(f"Timestamp: {TIMESTAMP}")
    
    # Check if py-spy is available
    try:
        subprocess.run(["uv", "run", "py-spy", "--version"], capture_output=True, check=True)
        print("✓ py-spy is available")
    except Exception as e:
        print(f"✗ py-spy not available: {e}")
        sys.exit(1)
    
    # Profile each strategy
    for strategy_name, info in STRATEGIES.items():
        strategy_file = info["file"]
        
        # Check if file exists
        if not (project_root / strategy_file).exists():
            print(f"\n⚠ Strategy file not found: {strategy_file}")
            continue
        
        print(f"\nProfiling: {info['description']}")
        
        # Run full profiling (flamegraph + speedscope + raw)
        run_py_spy_profile(strategy_name, strategy_file, duration=120)
        
        # Small delay between runs
        time.sleep(2)
    
    print(f"\n{'='*60}")
    print("Profiling complete!")
    print(f"Results in: {PROFILING_DIR}")
    print(f"{'='*60}")
    
    # List generated files
    print("\nGenerated files:")
    for f in sorted(PROFILING_DIR.glob(f"*{TIMESTAMP}*")):
        size = f.stat().st_size / 1024
        print(f"  {f.name} ({size:.1f} KB)")

if __name__ == "__main__":
    main()