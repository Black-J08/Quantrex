"""ForwardReturnAggregator - Comprehensive statistics computation."""

from datetime import timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

from quantrex_research.research_components.forward_return.models import ForwardReturnResult, ForwardReturnSeries


class ForwardReturnAggregator:
    """Aggregates forward return series into comprehensive statistics.
    
    Computes: count, mean, median, std, min, max, quantiles (25/50/75/90/95/99),
    positive_prob, skewness, excess_kurtosis, VaR_95, CVaR_95, VaR_99, CVaR_99, tail_ratio
    """
    
    QUANTILES = [0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    
    @staticmethod
    def aggregate(series_list: List[ForwardReturnSeries]) -> ForwardReturnResult:
        """Aggregate multiple ForwardReturnSeries into statistics per horizon.
        
        Args:
            series_list: List of ForwardReturnSeries from multiple events.
            
        Returns:
            ForwardReturnResult with statistics and raw returns per horizon.
        """
        if not series_list:
            return ForwardReturnResult(horizon_stats={}, raw_returns={})
        
        # Collect all horizons from all series
        all_horizons = set()
        for series in series_list:
            all_horizons.update(series.returns.keys())
        
        horizon_stats: Dict[timedelta, Dict[str, float]] = {}
        raw_returns: Dict[timedelta, List[float]] = {}
        
        for horizon in sorted(all_horizons):
            # Collect valid returns for this horizon
            returns = []
            for series in series_list:
                ret = series.returns.get(horizon)
                if ret is not None:
                    returns.append(ret)
            
            if not returns:
                # No valid returns for this horizon
                horizon_stats[horizon] = {
                    "count": 0,
                    "mean": float("nan"),
                    "median": float("nan"),
                    "std": float("nan"),
                    "min": float("nan"),
                    "max": float("nan"),
                    "positive_prob": float("nan"),
                    "skewness": float("nan"),
                    "excess_kurtosis": float("nan"),
                    "VaR_95": float("nan"),
                    "CVaR_95": float("nan"),
                    "VaR_99": float("nan"),
                    "CVaR_99": float("nan"),
                    "tail_ratio": float("nan"),
                }
                for q in ForwardReturnAggregator.QUANTILES:
                    horizon_stats[horizon][f"quantile_{int(q*100)}"] = float("nan")
                raw_returns[horizon] = []
                continue
            
            returns_array = np.array(returns)
            raw_returns[horizon] = returns
            
            # Basic statistics
            count = len(returns)
            mean = float(np.mean(returns_array))
            median = float(np.median(returns_array))
            std = float(np.std(returns_array, ddof=1)) if count > 1 else 0.0
            min_val = float(np.min(returns_array))
            max_val = float(np.max(returns_array))
            
            # Quantiles
            quantiles = {}
            for q in ForwardReturnAggregator.QUANTILES:
                quantiles[f"quantile_{int(q*100)}"] = float(np.quantile(returns_array, q))
            
            # Positive return probability
            positive_count = np.sum(returns_array > 0)
            positive_prob = float(positive_count / count)
            
            # Skewness and excess kurtosis
            if count >= 3 and std > 0:
                skewness = float(pd.Series(returns).skew())
                excess_kurtosis = float(pd.Series(returns).kurtosis())
            else:
                skewness = 0.0
                excess_kurtosis = 0.0
            
            # Value at Risk (VaR) and Conditional VaR (CVaR)
            var_95 = float(np.percentile(returns_array, 5))  # 5th percentile = 95% VaR
            var_99 = float(np.percentile(returns_array, 1))  # 1st percentile = 99% VaR
            
            # CVaR (Expected Shortfall) - average of returns below VaR
            cvar_95 = float(np.mean(returns_array[returns_array <= var_95])) if np.any(returns_array <= var_95) else var_95
            cvar_99 = float(np.mean(returns_array[returns_array <= var_99])) if np.any(returns_array <= var_99) else var_99
            
            # Tail Ratio: ratio of right tail (95th percentile) to left tail (5th percentile)
            p95 = np.percentile(returns_array, 95)
            p05 = np.percentile(returns_array, 5)
            tail_ratio = float(abs(p95 / p05)) if p05 != 0 else float("inf")
            
            horizon_stats[horizon] = {
                "count": count,
                "mean": mean,
                "median": median,
                "std": std,
                "min": min_val,
                "max": max_val,
                "positive_prob": positive_prob,
                "skewness": skewness,
                "excess_kurtosis": excess_kurtosis,
                "VaR_95": var_95,
                "CVaR_95": cvar_95,
                "VaR_99": var_99,
                "CVaR_99": cvar_99,
                "tail_ratio": tail_ratio,
                **quantiles,
            }
        
        return ForwardReturnResult(horizon_stats=horizon_stats, raw_returns=raw_returns)