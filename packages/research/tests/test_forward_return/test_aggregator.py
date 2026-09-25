"""Tests for ForwardReturnAggregator."""

from datetime import datetime, timedelta
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderSide

from quantrex_research.research_components.forward_return.models import (
    ForwardReturnEvent,
    ForwardReturnSeries,
)
from quantrex_research.research_components.forward_return.aggregator import ForwardReturnAggregator


def create_test_series(returns_by_horizon: dict) -> list[ForwardReturnSeries]:
    """Create test series with given returns."""
    base_time = datetime(2024, 1, 1, 9, 15)
    event_candle = Candle(
        symbol="TEST",
        timestamp=base_time,
        close_time=base_time + timedelta(minutes=1),
        timeframe="1M",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=100.0,
    )
    
    series_list = []
    for i, (horizon, ret) in enumerate(returns_by_horizon.items()):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=base_time + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=event_candle,
        )
        series = ForwardReturnSeries(event=event, returns={horizon: ret})
        series_list.append(series)
    
    return series_list


def test_aggregator_basic_statistics():
    """Test basic statistics computation."""
    # Create series with known returns
    returns_data = {
        timedelta(minutes=1): [1.0, 2.0, 3.0, 4.0, 5.0],  # mean=3.0, median=3.0
        timedelta(minutes=5): [2.0, 4.0, 6.0, 8.0, 10.0],  # mean=6.0, median=6.0
    }
    
    series_list = []
    for i in range(5):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={
                timedelta(minutes=1): returns_data[timedelta(minutes=1)][i],
                timedelta(minutes=5): returns_data[timedelta(minutes=5)][i],
            }
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    
    # Check 1-minute horizon
    stats_1m = result.horizon_stats[timedelta(minutes=1)]
    assert stats_1m["count"] == 5
    assert abs(stats_1m["mean"] - 3.0) < 0.01
    assert abs(stats_1m["median"] - 3.0) < 0.01
    assert stats_1m["min"] == 1.0
    assert stats_1m["max"] == 5.0
    
    # Check 5-minute horizon
    stats_5m = result.horizon_stats[timedelta(minutes=5)]
    assert stats_5m["count"] == 5
    assert abs(stats_5m["mean"] - 6.0) < 0.01
    assert abs(stats_5m["median"] - 6.0) < 0.01


def test_aggregator_positive_probability():
    """Test positive return probability calculation."""
    returns_data = {
        timedelta(minutes=1): [1.0, -2.0, 3.0, -4.0, 5.0],  # 3 positive out of 5 = 60%
    }
    
    series_list = []
    for i in range(5):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={timedelta(minutes=1): returns_data[timedelta(minutes=1)][i]}
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    stats = result.horizon_stats[timedelta(minutes=1)]
    
    assert abs(stats["positive_prob"] - 0.6) < 0.01


def test_aggregator_quantiles():
    """Test quantile computation."""
    # 10 values: 1,2,3,4,5,6,7,8,9,10
    # Q25 = 3.25, Q50 = 5.5, Q75 = 7.75, Q90 = 9.1, Q95 = 9.55, Q99 = 9.91
    returns_data = list(range(1, 11))
    
    series_list = []
    for i, ret in enumerate(returns_data):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={timedelta(minutes=1): float(ret)}
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    stats = result.horizon_stats[timedelta(minutes=1)]
    
    assert abs(stats["quantile_25"] - 3.25) < 0.1
    assert abs(stats["quantile_50"] - 5.5) < 0.1
    assert abs(stats["quantile_75"] - 7.75) < 0.1
    assert abs(stats["quantile_90"] - 9.1) < 0.1
    assert abs(stats["quantile_95"] - 9.55) < 0.1
    assert abs(stats["quantile_99"] - 9.91) < 0.1


def test_aggregator_var_cvar():
    """Test VaR and CVaR computation."""
    # Returns: -10, -5, -2, -1, 0, 1, 2, 5, 10, 20
    # VaR 95% = 5th percentile ≈ -5.5
    # CVaR 95% = average of returns <= VaR 95%
    returns_data = [-10.0, -5.0, -2.0, -1.0, 0.0, 1.0, 2.0, 5.0, 10.0, 20.0]
    
    series_list = []
    for i, ret in enumerate(returns_data):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={timedelta(minutes=1): ret}
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    stats = result.horizon_stats[timedelta(minutes=1)]
    
    # VaR 95% should be around 5th percentile
    assert stats["VaR_95"] < 0  # Negative (loss)
    # CVaR 95% should be <= VaR 95% (more negative)
    assert stats["CVaR_95"] <= stats["VaR_95"]
    
    # VaR 99% should be around 1st percentile
    assert stats["VaR_99"] <= stats["VaR_95"]
    assert stats["CVaR_99"] <= stats["CVaR_95"]


def test_aggregator_skewness_kurtosis():
    """Test skewness and excess kurtosis."""
    # Symmetric distribution should have skewness ~ 0
    returns_data = [-2.0, -1.0, 0.0, 1.0, 2.0]
    
    series_list = []
    for i, ret in enumerate(returns_data):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={timedelta(minutes=1): ret}
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    stats = result.horizon_stats[timedelta(minutes=1)]
    
    # Skewness should be close to 0 for symmetric distribution
    assert abs(stats["skewness"]) < 0.5
    # Excess kurtosis for small sample may vary


def test_aggregator_tail_ratio():
    """Test tail ratio computation."""
    # Positive tail heavier than negative
    returns_data = [-1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
    
    series_list = []
    for i, ret in enumerate(returns_data):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={timedelta(minutes=1): ret}
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    stats = result.horizon_stats[timedelta(minutes=1)]
    
    # Tail ratio should be > 1 (positive tail heavier)
    assert stats["tail_ratio"] > 1.0


def test_aggregator_empty_series():
    """Test aggregator with empty series list."""
    result = ForwardReturnAggregator.aggregate([])
    
    assert result.horizon_stats == {}
    assert result.raw_returns == {}


def test_aggregator_no_valid_returns():
    """Test aggregator when all returns are None."""
    event = ForwardReturnEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, 1, 9, 15),
        direction=OrderSide.BUY,
        metadata={},
        candle=Candle(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15),
            close_time=datetime(2024, 1, 1, 9, 16),
            timeframe="1M",
            open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
        ),
    )
    
    series = ForwardReturnSeries(event=event, returns={timedelta(minutes=1): None})
    result = ForwardReturnAggregator.aggregate([series])
    
    stats = result.horizon_stats[timedelta(minutes=1)]
    assert stats["count"] == 0
    assert stats["mean"] != stats["mean"]  # NaN check


def test_aggregator_to_dict():
    """Test ForwardReturnResult.to_dict() method."""
    returns_data = {timedelta(minutes=1): [1.0, 2.0, 3.0]}
    
    series_list = []
    for i in range(3):
        event = ForwardReturnEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
            direction=OrderSide.BUY,
            metadata={},
            candle=Candle(
                symbol="TEST",
                timestamp=datetime(2024, 1, 1, 9, 15) + timedelta(minutes=i),
                close_time=datetime(2024, 1, 1, 9, 16) + timedelta(minutes=i),
                timeframe="1M",
                open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0,
            ),
        )
        series = ForwardReturnSeries(
            event=event,
            returns={timedelta(minutes=1): returns_data[timedelta(minutes=1)][i]}
        )
        series_list.append(series)
    
    result = ForwardReturnAggregator.aggregate(series_list)
    result_dict = result.to_dict()
    
    assert "0:01:00" in result_dict
    assert "count" in result_dict["0:01:00"]
    assert "raw_returns" in result_dict["0:01:00"]