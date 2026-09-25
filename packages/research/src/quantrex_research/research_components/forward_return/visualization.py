"""Forward Return Visualization - Plot generation with embedded statistics."""

from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


def plot_distribution(
    returns: List[float],
    horizon: timedelta,
    statistics: Dict[str, float],
    output_path: Path,
    title: Optional[str] = None,
) -> None:
    """Plot histogram + KDE + Normal overlay with embedded statistics panel.
    
    Args:
        returns: List of percentage returns for this horizon.
        horizon: The time horizon.
        statistics: Statistics dictionary from aggregator.
        output_path: Path to save the plot.
        title: Optional custom title.
    """
    if not returns:
        return
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    returns_array = np.array(returns)
    
    # Histogram
    n, bins, patches = ax.hist(
        returns_array, bins=50, density=True, alpha=0.6, 
        color="steelblue", edgecolor="white", linewidth=0.5,
        label="Empirical Distribution"
    )
    
    # KDE
    if len(returns) > 1:
        kde = stats.gaussian_kde(returns_array)
        x_range = np.linspace(returns_array.min(), returns_array.max(), 200)
        ax.plot(x_range, kde(x_range), "r-", linewidth=2, label="KDE")
    
    # Normal distribution overlay
    mean = statistics.get("mean", 0)
    std = statistics.get("std", 1)
    if std > 0:
        x_range = np.linspace(returns_array.min(), returns_array.max(), 200)
        normal_pdf = stats.norm.pdf(x_range, mean, std)
        ax.plot(x_range, normal_pdf, "g--", linewidth=2, label="Normal Distribution")
    
    # Statistics panel text
    stats_text = (
        f"Horizon: {horizon}\n"
        f"Count: {int(statistics.get('count', 0))}\n"
        f"Mean: {statistics.get('mean', 0):.4f}%\n"
        f"Median: {statistics.get('median', 0):.4f}%\n"
        f"Std: {statistics.get('std', 0):.4f}%\n"
        f"Min: {statistics.get('min', 0):.4f}%\n"
        f"Max: {statistics.get('max', 0):.4f}%\n"
        f"Positive Prob: {statistics.get('positive_prob', 0):.2%}\n"
        f"Skewness: {statistics.get('skewness', 0):.4f}\n"
        f"Excess Kurtosis: {statistics.get('excess_kurtosis', 0):.4f}\n"
        f"VaR 95%: {statistics.get('VaR_95', 0):.4f}%\n"
        f"CVaR 95%: {statistics.get('CVaR_95', 0):.4f}%\n"
        f"VaR 99%: {statistics.get('VaR_99', 0):.4f}%\n"
        f"CVaR 99%: {statistics.get('CVaR_99', 0):.4f}%\n"
        f"Tail Ratio: {statistics.get('tail_ratio', 0):.4f}"
    )
    
    # Add quantiles
    for q in [25, 50, 75, 90, 95, 99]:
        key = f"quantile_{q}"
        if key in statistics:
            stats_text += f"\nQ{q}: {statistics[key]:.4f}%"
    
    # Place statistics panel
    ax.text(
        0.98, 0.98, stats_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        horizontalalignment="right",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="wheat", alpha=0.9)
    )
    
    ax.set_xlabel("Percentage Return (%)")
    ax.set_ylabel("Density")
    ax.set_title(title or f"Forward Return Distribution — {horizon}")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_qq(
    returns: List[float],
    horizon: timedelta,
    output_path: Path,
    title: Optional[str] = None,
) -> None:
    """Plot Q-Q plot vs normal distribution with tail deviation annotation.
    
    Args:
        returns: List of percentage returns for this horizon.
        horizon: The time horizon.
        output_path: Path to save the plot.
        title: Optional custom title.
    """
    if not returns:
        return
    
    fig, ax = plt.subplots(figsize=(8, 8))
    
    returns_array = np.array(returns)
    
    # Q-Q plot
    stats.probplot(returns_array, dist="norm", plot=ax)
    
    # Get the line for annotation
    line = ax.get_lines()[0]
    x_data = line.get_xdata()
    y_data = line.get_ydata()
    
    # Annotate tail deviations
    if len(x_data) > 10:
        # Left tail (bottom 5%)
        left_idx = int(len(x_data) * 0.05)
        right_idx = int(len(x_data) * 0.95)
        
        left_dev = y_data[left_idx] - x_data[left_idx]
        right_dev = y_data[right_idx] - x_data[right_idx]
        
        ax.annotate(
            f"Left tail deviation: {left_dev:.4f}",
            xy=(x_data[left_idx], y_data[left_idx]),
            xytext=(x_data[left_idx] - 1, y_data[left_idx] + 0.5),
            arrowprops=dict(arrowstyle="->", color="red"),
            fontsize=9, color="red"
        )
        ax.annotate(
            f"Right tail deviation: {right_dev:.4f}",
            xy=(x_data[right_idx], y_data[right_idx]),
            xytext=(x_data[right_idx] + 0.5, y_data[right_idx] - 0.5),
            arrowprops=dict(arrowstyle="->", color="red"),
            fontsize=9, color="red"
        )
    
    ax.set_title(title or f"Q-Q Plot vs Normal — {horizon}")
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_tail_comparison(
    returns: List[float],
    horizon: timedelta,
    statistics: Dict[str, float],
    output_path: Path,
    title: Optional[str] = None,
) -> None:
    """Plot conditional density: positive vs negative returns with tail metrics.
    
    Args:
        returns: List of percentage returns for this horizon.
        horizon: The time horizon.
        statistics: Statistics dictionary from aggregator.
        output_path: Path to save the plot.
        title: Optional custom title.
    """
    if not returns:
        return
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    returns_array = np.array(returns)
    positive_returns = returns_array[returns_array > 0]
    negative_returns = returns_array[returns_array < 0]
    
    # Left: Positive returns distribution
    if len(positive_returns) > 0:
        ax1.hist(positive_returns, bins=30, density=True, alpha=0.7, 
                 color="green", edgecolor="white", label=f"Positive (n={len(positive_returns)})")
        if len(positive_returns) > 1:
            kde = stats.gaussian_kde(positive_returns)
            x_range = np.linspace(positive_returns.min(), positive_returns.max(), 100)
            ax1.plot(x_range, kde(x_range), "g-", linewidth=2)
    ax1.set_xlabel("Positive Return (%)")
    ax1.set_ylabel("Density")
    ax1.set_title("Positive Returns Distribution")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Right: Negative returns distribution
    if len(negative_returns) > 0:
        ax2.hist(negative_returns, bins=30, density=True, alpha=0.7,
                 color="red", edgecolor="white", label=f"Negative (n={len(negative_returns)})")
        if len(negative_returns) > 1:
            kde = stats.gaussian_kde(negative_returns)
            x_range = np.linspace(negative_returns.min(), negative_returns.max(), 100)
            ax2.plot(x_range, kde(x_range), "r-", linewidth=2)
    ax2.set_xlabel("Negative Return (%)")
    ax2.set_ylabel("Density")
    ax2.set_title("Negative Returns Distribution")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Add tail metrics as text
    tail_text = (
        f"Horizon: {horizon}\n"
        f"Positive Count: {len(positive_returns)}\n"
        f"Negative Count: {len(negative_returns)}\n"
        f"Positive Prob: {statistics.get('positive_prob', 0):.2%}\n"
        f"VaR 95%: {statistics.get('VaR_95', 0):.4f}%\n"
        f"CVaR 95%: {statistics.get('CVaR_95', 0):.4f}%\n"
        f"Tail Ratio: {statistics.get('tail_ratio', 0):.4f}"
    )
    
    fig.text(
        0.5, 0.02, tail_text,
        fontsize=10, ha="center", fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8)
    )
    
    plt.suptitle(title or f"Tail Comparison — {horizon}")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_horizon_comparison(
    all_horizon_stats: Dict[timedelta, Dict[str, float]],
    output_path: Path,
    title: Optional[str] = None,
) -> None:
    """Plot multi-horizon comparison: mean/std/positive_prob/VaR across all horizons.
    
    Args:
        all_horizon_stats: Dictionary mapping horizon to statistics.
        output_path: Path to save the plot.
        title: Optional custom title.
    """
    if not all_horizon_stats:
        return
    
    horizons = sorted(all_horizon_stats.keys())
    horizon_labels = [str(h) for h in horizons]
    
    means = [all_horizon_stats[h].get("mean", 0) for h in horizons]
    stds = [all_horizon_stats[h].get("std", 0) for h in horizons]
    positive_probs = [all_horizon_stats[h].get("positive_prob", 0) for h in horizons]
    var_95 = [all_horizon_stats[h].get("VaR_95", 0) for h in horizons]
    cvar_95 = [all_horizon_stats[h].get("CVaR_95", 0) for h in horizons]
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Mean return
    axes[0, 0].bar(horizon_labels, means, color="steelblue", alpha=0.7, edgecolor="white")
    axes[0, 0].axhline(y=0, color="black", linewidth=0.5)
    axes[0, 0].set_title("Mean Return by Horizon")
    axes[0, 0].set_ylabel("Mean Return (%)")
    axes[0, 0].tick_params(axis="x", rotation=45)
    axes[0, 0].grid(True, alpha=0.3)
    
    # Std deviation
    axes[0, 1].bar(horizon_labels, stds, color="orange", alpha=0.7, edgecolor="white")
    axes[0, 1].set_title("Std Deviation by Horizon")
    axes[0, 1].set_ylabel("Std Dev (%)")
    axes[0, 1].tick_params(axis="x", rotation=45)
    axes[0, 1].grid(True, alpha=0.3)
    
    # Positive probability
    axes[1, 0].bar(horizon_labels, positive_probs, color="green", alpha=0.7, edgecolor="white")
    axes[1, 0].axhline(y=0.5, color="black", linewidth=0.5, linestyle="--")
    axes[1, 0].set_title("Positive Return Probability by Horizon")
    axes[1, 0].set_ylabel("Probability")
    axes[1, 0].set_ylim(0, 1)
    axes[1, 0].tick_params(axis="x", rotation=45)
    axes[1, 0].grid(True, alpha=0.3)
    
    # VaR 95% and CVaR 95%
    x = np.arange(len(horizon_labels))
    width = 0.35
    axes[1, 1].bar(x - width/2, var_95, width, label="VaR 95%", color="red", alpha=0.7, edgecolor="white")
    axes[1, 1].bar(x + width/2, cvar_95, width, label="CVaR 95%", color="darkred", alpha=0.7, edgecolor="white")
    axes[1, 1].set_title("VaR & CVaR 95% by Horizon")
    axes[1, 1].set_ylabel("Return (%)")
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(horizon_labels, rotation=45)
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.suptitle(title or "Multi-Horizon Forward Return Comparison")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()