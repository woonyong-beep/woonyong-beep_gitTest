"""미래 정보 차단 테스트: 미래 가격을 바꿔도 과거 결정은 그대로여야 한다."""

import numpy as np
import pytest

from backtest import data, engine
from backtest.engine import Weights
from backtest.strategies import InfiniteBuy


def make_prices(seed=0, n=300):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))


def series(values, name="A"):
    d = np.datetime64("2020-01-01", "D") + np.arange(len(values))
    return data.Series(name, d, np.asarray(values, float))


class Momentum:
    """t 일까지 이력 전체를 쓰는 전략: 종가가 이력 평균보다 높으면 100%, 아니면 0%."""

    def reset(self):
        self.log = []

    def on_bar(self, ctx):
        h = ctx.prices["A"]
        w = 1.0 if h[-1] > h.mean() else 0.0
        self.log.append((ctx.t, len(h), w))
        return Weights({"A": w})


@pytest.mark.parametrize("make", [Momentum, lambda: InfiniteBuy("A", splits=10, take_profit=0.05)])
def test_future_change_does_not_change_past(make):
    p = make_prices()
    k = 150
    q = p.copy()
    q[k + 1:] *= np.random.default_rng(1).uniform(0.5, 1.5, len(p) - k - 1)   # 미래만 바꾼다
    r1 = engine.run(make(), series(p))
    r2 = engine.run(make(), series(q))
    t1 = [tr for tr in r1.trades if tr[0] <= k]
    t2 = [tr for tr in r2.trades if tr[0] <= k]
    assert t1 == t2 and len(t1) > 0
    assert np.array_equal(r1.wealth[: k + 1], r2.wealth[: k + 1])
    assert np.array_equal(r1.shares[: k + 1], r2.shares[: k + 1])
    # 미래를 바꾸었으니 이후 결과는 달라진다 (테스트가 실제로 무언가를 확인하는지 점검)
    assert not np.array_equal(r1.wealth, r2.wealth)


def test_momentum_sees_exactly_t_plus_one_prices():
    s = Momentum()
    engine.run(s, series(make_prices(n=20)))
    assert all(n == t + 1 for t, n, _ in s.log)


def test_strategy_cannot_reach_future():
    seen = {}

    def snoop(ctx):
        h = ctx.prices["A"]
        with pytest.raises(IndexError):
            h[ctx.t + 1]
        base = h.base if h.base is not None else h
        seen[ctx.t] = np.asarray(base)[ctx.t + 1:].copy()       # 버퍼 전체를 꺼내 봐도
        assert len(ctx.dates) == ctx.t + 1
        with pytest.raises(ValueError):
            h[0] = 0.0                                          # 읽기 전용
        return None

    engine.run(snoop, series(make_prices(n=30)))
    assert all(np.isnan(v).all() for v in seen.values())         # 미래 칸은 비어 있다


def test_tampering_with_history_does_not_change_results():
    p = make_prices(n=50)

    def tamper(ctx):
        h = ctx.prices["A"]
        base = h.base
        base.flags.writeable = True
        base[: ctx.t + 1] = 1e-9                                 # 전략이 버퍼를 망가뜨려도
        return Weights({"A": 1.0}) if ctx.t == 0 else None

    r = engine.run(tamper, series(p))
    assert np.allclose(r.wealth, p / p[0])                       # 체결/평가는 엔진 원본으로 한다
