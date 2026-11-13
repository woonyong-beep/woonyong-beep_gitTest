"""엔진과 데이터 불러오기를 손으로 계산한 작은 예와 비교한다."""

import numpy as np
import pytest

from backtest import data, engine, metrics
from backtest.engine import Trades, Weights
from backtest.strategies import BuyAndHold, ConstantWeight, InfiniteBuy, SplitBuy


def series(name, values, start="2024-01-01"):
    d = np.datetime64(start, "D") + np.arange(len(values))
    return data.Series(name, d, np.array(values, float))


def test_buy_and_hold():
    r = engine.run(BuyAndHold("A"), series("A", [10, 11, 12.1]))
    assert np.allclose(r.wealth, [1, 1.1, 1.21])
    assert len(r.trades) == 1 and r.trades[0][2] == "A"
    assert r.exposure == pytest.approx(1.0)


def test_trading_cost_bps():
    # 첫날 전액 매수 (체결 금액 1) 에 10bp -> 현금 -0.001
    r = engine.run(BuyAndHold("A"), series("A", [10, 11, 12.1]), cost_bps=10)
    assert np.allclose(r.wealth, [0.999, 1.099, 1.209])
    assert r.total_cost == pytest.approx(0.001)


def test_constant_rf_cash_only():
    r = engine.run(lambda ctx: None, series("A", [1, 2, 3, 4]), rf=0.0252)
    g = np.exp(0.0252 / 252)
    assert np.allclose(r.wealth, [1, g, g**2, g**3])
    assert np.allclose(r.rf_returns, g - 1)


def test_rate_series_uses_previous_day_rate():
    px = data.Series("A", np.array(["2024-01-05", "2024-01-08", "2024-01-09"], dtype="datetime64[D]"),
                     np.array([1.0, 1.0, 1.0]))
    rate = data.Series("DTB3", np.array(["2024-01-04", "2024-01-08"], dtype="datetime64[D]"),
                       np.array([3.6, 7.2]))
    r = engine.run(lambda ctx: None, px, rf=rate)
    # 01-05 -> 01-08: 01-05 이전 마지막 값 3.6%, 3일 ACT/360. 01-08 -> 01-09: 01-08 값 7.2%, 1일
    g1 = 1 + 0.036 * 3 / 360
    g2 = 1 + 0.072 * 1 / 360
    assert np.allclose(r.wealth, [1, g1, g1 * g2])
    with pytest.raises(ValueError):
        engine.run(lambda ctx: None, px, rf=rate.between("2024-01-06"))


def test_constant_weight_two_assets():
    a = series("A", [1, 2, 2])
    b = series("B", [1, 1, 0.5])
    r = engine.run(ConstantWeight({"A": 0.5, "B": 0.5}), [a, b])
    # 1일차: 0.5*2 + 0.5*1 = 1.5, 리밸런싱 후 2일차: 0.75*1 + 0.75*0.5 = 1.125
    assert np.allclose(r.wealth, [1, 1.5, 1.125])
    assert np.allclose(r.weights[0], [0.5, 0.5]) and np.allclose(r.weights[1], [0.5, 0.5])


def test_weights_zero_sells_everything():
    def strat(ctx):
        return Weights({"A": 1.0}) if ctx.t == 0 else Weights({"A": 0.0})
    r = engine.run(strat, series("A", [10, 20, 5]))
    assert r.shares[1, 0] == 0.0
    assert np.allclose(r.wealth, [1, 2, 2])


def test_trades_and_list_of_orders():
    def strat(ctx):
        if ctx.t == 0:
            return [Trades({"A": 0.25}), Trades({"A": 0.25})]
        return None
    r = engine.run(strat, series("A", [10, 20, 20]))
    assert r.shares[0, 0] == pytest.approx(0.05)
    assert np.allclose(r.wealth, [1, 1.5, 1.5])


def test_lag_one_executes_next_close():
    r = engine.run(BuyAndHold("A"), series("A", [10, 20, 40]), lag=1)
    # 0일에 결정, 1일 종가 20 에 체결 -> 1일 1.0, 2일 2.0
    assert np.allclose(r.wealth, [1, 1, 2])


def test_last_day_takes_no_orders():
    calls = []
    engine.run(lambda ctx: calls.append(ctx.t), series("A", [1, 2, 3]))
    assert calls == [0, 1]


def test_bad_order_type():
    with pytest.raises(TypeError):
        engine.run(lambda ctx: {"A": 1.0}, series("A", [1, 2]))


def test_split_buy_matches_closed_form():
    p = np.array([10, 9, 11, 12, 8, 10.0])
    r = engine.run(SplitBuy("A", splits=3), series("A", p), rf=0.03)
    g = np.exp(0.03 / 252)
    expected = (g ** np.arange(3) * p[-1] / p[:3]).mean()
    assert r.wealth[-1] == pytest.approx(expected)


def test_infinite_buy_small_example():
    # 4분할, 익절 10%. 0일 1/4 매수 (가격 10), 1일 1/4 매수 (가격 10), 2일 가격 11.5: 평가 0.575 >= 0.55 -> 매도
    s = InfiniteBuy("A", splits=4, take_profit=0.10)
    r = engine.run(s, series("A", [10, 10, 11.5, 11.5]))
    assert s.cycles == [(0, 2)]
    assert r.wealth[2] == pytest.approx(1 + 0.5 * 0.15)
    assert r.shares[2, 0] == 0.0


def test_data_validation(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("date,adj_close\n2024-01-02,1\n2024-01-01,2\n")
    with pytest.raises(ValueError, match="정렬"):
        data.load_csv(p)
    p.write_text("date,adj_close\n2024-01-01,1\n2024-01-01,2\n")
    with pytest.raises(ValueError, match="정렬"):
        data.load_csv(p)
    p.write_text("date,adj_close\n2024-01-01,1\n2024-01-02,0\n")
    with pytest.raises(ValueError, match="0 이하"):
        data.load_csv(p)
    p.write_text("date,adj_close\n2024-01-01,1\n2024-01-02,\n")
    with pytest.raises(ValueError, match="빈"):
        data.load_csv(p)
    p.write_text("date,adj_close\n2024-01-01,1\n2024-01-02,-1\n")
    assert len(data.load_csv(p, positive=False)) == 2


def test_load_prefers_adj_close(tmp_path):
    p = tmp_path / "y.csv"
    p.write_text("date,open,high,low,close,adj_close,volume\n2024-01-01,,,,10,9,\n2024-01-02,,,,11,10,\n")
    assert data.load_csv(p).values.tolist() == [9, 10]
    p.write_text("date,open,high,low,close,adj_close,volume\n2024-01-01,,,,10,,\n2024-01-02,,,,11,,\n")
    assert data.load_csv(p).values.tolist() == [10, 11]


def test_align_intersection():
    a = data.Series("A", np.array(["2024-01-01", "2024-01-02", "2024-01-03"], dtype="datetime64[D]"),
                    np.array([1.0, 2, 3]))
    b = data.Series("B", np.array(["2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]"),
                    np.array([20.0, 30, 40]))
    d, v = data.align(a, b)
    assert d.astype(str).tolist() == ["2024-01-02", "2024-01-03"]
    assert v["A"].tolist() == [2, 3] and v["B"].tolist() == [20, 30]


def test_summary_runs():
    r = engine.run(BuyAndHold("A"), series("A", [10, 11, 9, 12]))
    m = metrics.summary(r, budget=100)
    assert m["final"] == pytest.approx(120)
    assert m["mdd"] == pytest.approx(9 / 11 - 1)
