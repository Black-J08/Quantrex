"""Tests for LiveStream data feed."""

import pytest

from quantrex.engine.live_engine.data_feed.stream import LiveStream


class TestLiveStream:
    """Tests for LiveStream."""

    def test_subscribe_sets_subscribed(self) -> None:
        stream = LiveStream("RELIANCE")
        assert not stream.is_subscribed()
        stream.subscribe()
        assert stream.is_subscribed()

    def test_iter_without_subscribe_raises(self) -> None:
        stream = LiveStream("RELIANCE")
        with pytest.raises(RuntimeError, match="stream not subscribed"):
            iter(stream)
