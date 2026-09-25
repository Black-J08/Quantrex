"""Tests for Forward Return Visualization."""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from quantrex_research.research_components.forward_return.visualization import (
    plot_distribution,
    plot_qq,
    plot_tail_comparison,
    plot_horizon_comparison,
)


def test_plot_distribution():
    """Test distribution plot generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_distribution.png"
        
        returns = [1.0, 2.0, -1.0, 0.5, -0.5, 3.0, -2.0, 1.5, -1.5, 0.0]
        stats = {
            "count": 10,
            "mean": 0.4,
            "median": 0.25,
            "std": 1.5,
            "min": -2.0,
            "max": 3.0,
            "positive_prob": 0.6,
            "skewness": 0.2,
            "excess_kurtosis": -0.5,
            "VaR_95": -1.8,
            "CVaR_95": -1.9,
            "VaR_99": -2.0,
            "CVaR_99": -2.0,
            "tail_ratio": 1.5,
            "quantile_25": -1.0,
            "quantile_50": 0.25,
            "quantile_75": 1.5,
            "quantile_90": 2.5,
            "quantile_95": 2.8,
            "quantile_99": 3.0,
        }
        
        plot_distribution(returns, timedelta(minutes=5), stats, output_path)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_plot_qq():
    """Test Q-Q plot generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_qq.png"
        
        returns = [1.0, 2.0, -1.0, 0.5, -0.5, 3.0, -2.0, 1.5, -1.5, 0.0]
        
        plot_qq(returns, timedelta(minutes=5), output_path)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_plot_tail_comparison():
    """Test tail comparison plot generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_tail.png"
        
        returns = [1.0, 2.0, -1.0, 0.5, -0.5, 3.0, -2.0, 1.5, -1.5, 0.0]
        stats = {
            "positive_prob": 0.6,
            "VaR_95": -1.8,
            "CVaR_95": -1.9,
            "tail_ratio": 1.5,
        }
        
        plot_tail_comparison(returns, timedelta(minutes=5), stats, output_path)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_plot_horizon_comparison():
    """Test horizon comparison plot generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_horizon.png"
        
        all_horizon_stats = {
            timedelta(minutes=1): {
                "mean": 0.5, "std": 1.0, "positive_prob": 0.55,
                "VaR_95": -1.5, "CVaR_95": -1.8,
            },
            timedelta(minutes=5): {
                "mean": 1.0, "std": 2.0, "positive_prob": 0.6,
                "VaR_95": -3.0, "CVaR_95": -3.5,
            },
            timedelta(minutes=15): {
                "mean": 1.5, "std": 3.0, "positive_prob": 0.65,
                "VaR_95": -4.5, "CVaR_95": -5.0,
            },
        }
        
        plot_horizon_comparison(all_horizon_stats, output_path)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_plot_empty_returns():
    """Test that plots handle empty returns gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_empty.png"
        
        returns = []
        stats = {}
        
        # Should not raise, just return early
        plot_distribution(returns, timedelta(minutes=5), stats, output_path)
        plot_qq(returns, timedelta(minutes=5), output_path)
        plot_tail_comparison(returns, timedelta(minutes=5), stats, output_path)
        
        # Files should not be created for empty returns
        assert not output_path.exists()