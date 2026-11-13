"""새 엔진이 research/backtest_tqqq.py (a) 의 TQQQ 수치를 그대로 재현하는지 확인한다.

데이터는 research/backtest_tqqq.py 와 같은 data/prices/yahoo/TQQQ.csv 의 adj_close 에서
2010-02-11 ~ 2026-11-11 (4214행) 만 잘라 쓴다.
기대값 (research/backtest_tqqq.py 출력, 예산 100):
  기준군 29,456 / 40일 분할매수 후 보유 24,420 / 무한매수법 22,848 / 일정비중 70% 12,272
  완료 사이클 72회, 평균 주식 비중 70.1%, 가장 오래 걸린 사이클 780거래일 (2021-11-01 ~ 2024-12-06)

collect.py 가 이 파일을 다시 받아도 깨지지 않게 한 것
- 행이 덧붙는 경우: 끝 날짜를 END 로 고정해 자른다. 파일 길이에 기대지 않는다.
- Yahoo 가 END 이후의 새 배당 때문에 과거 adj_close 전체에 같은 배수를 곱하는 경우: 모든 전략과 지표는
  가격 비율로만 계산되므로 그 배수에 바뀌지 않는다. 그래서 가격 수준(예: 첫날 값)은 확인하지 않는다.
  test_invariant_to_rebase_and_noise 가 이를 직접 확인한다.
- 다시 받을 때마다 adj_close 에 붙는 상대 1e-6 수준 잡음: 연속값은 반올림한 값의 일치 대신 상대/절대
  허용오차로 비교한다. 이산값(사이클 수, 날짜)은 정확히 비교하는데, 익절 판단이 경계에서 가장 가까웠던 날도
  기준과 상대 3.2e-5 (2015-05-27) 떨어져 있어 1e-6 수준 잡음으로는 바뀌지 않는다.
- 반대로 END 이전 구간의 일별 수익률이 바뀌면 (배당 날짜·금액 정정 등) 실제 데이터가 바뀐 것이므로
  이 테스트는 실패해야 한다. 그때는 research/backtest_tqqq.py, docs/tqqq-data.js, docs/index.html 의 수치를 함께
  다시 확인한다.
"""

import sys

import numpy as np
import pytest

from backtest import data, engine, metrics
from backtest.strategies import BuyAndHold, ConstantWeight, InfiniteBuy, SplitBuy
from tests.conftest import ROOT

RF = 0.03
BUDGET = 100
START, END = "2010-02-11", "2026-11-11"


@pytest.fixture(scope="module")
def tqqq():
    return data.load("yahoo", "TQQQ", start=START, end=END)


def run_all(tqqq):
    inf = InfiniteBuy("TQQQ", splits=40, take_profit=0.10)
    r_inf = engine.run(inf, tqqq, rf=RF)
    f = r_inf.exposure
    return dict(
        bh=engine.run(BuyAndHold("TQQQ"), tqqq, rf=RF),
        dca=engine.run(SplitBuy("TQQQ", splits=40), tqqq, rf=RF),
        inf=r_inf,
        cm=engine.run(ConstantWeight({"TQQQ": f}), tqqq, rf=RF),
        strategy=inf, f=f)


@pytest.fixture(scope="module")
def runs(tqqq):
    return run_all(tqqq)


FINAL = {"bh": 29456.316, "dca": 24420.403, "inf": 22847.675, "cm": 12272.278}


def test_data_window(tqqq):
    assert len(tqqq) == 4214
    assert str(tqqq.dates[0]) == START and str(tqqq.dates[-1]) == END


def test_final_wealth(runs):
    for k, v in FINAL.items():
        assert BUDGET * runs[k].wealth[-1] == pytest.approx(v, rel=1e-5), k


def test_infinite_buy_cycles_and_exposure(runs, tqqq):
    s = runs["strategy"]
    assert len(s.cycles) == 72
    assert runs["f"] == pytest.approx(0.701035, abs=1e-5)
    L, a, b = max(s.cycle_lengths(len(tqqq)))
    assert L == 780
    assert str(tqqq.dates[a]) == "2021-11-01" and str(tqqq.dates[b]) == "2024-12-06"
    D, a, b = max((b - a, a, b) for a, b in s.full_spells)
    assert (D, len(s.full_spells)) == (740, 31)


def test_metrics_table(runs):
    # research/backtest_tqqq.py (a) 표의 CAGR, 변동성, 샤프, 최대낙폭
    # 표에는 CAGR 40.4% / 38.9% / 38.3% / 33.3%, 변동성 61.3% / 61.3% / 48.9% / 43.0%,
    # 샤프 0.82 / 0.80 / 0.85 / 0.82, 최대낙폭 -81.7% / -81.7% / -81.1% / -65.9% 로 찍힌다.
    expected = {"bh": (0.404223, 0.613418, 0.816016, -0.816598),
                "dca": (0.388591, 0.612938, 0.797847, -0.816598),
                "inf": (0.383082, 0.488997, 0.847942, -0.810639),
                "cm": (0.332696, 0.430028, 0.816016, -0.659336)}
    for k, want in expected.items():
        m = metrics.summary(runs[k], budget=BUDGET)
        got = (m["cagr"], m["vol"], m["sharpe"], m["mdd"])
        assert got == pytest.approx(want, abs=1e-5), k
        assert str(m["mdd_date"]) == "2022-12-28"


def test_invariant_to_rebase_and_noise(tqqq, runs):
    """가격 전체에 상수배를 곱하거나 (Yahoo 의 배당 재조정) 상대 2e-6 잡음을 섞어도 (다시 받을 때의 차이)
    사이클과 날짜는 그대로이고 최종자산은 허용오차 안에 있는지."""
    rng = np.random.default_rng(0)
    for v in (tqqq.values * 0.9731, tqqq.values * (1 + rng.uniform(-2e-6, 2e-6, len(tqqq)))):
        other = run_all(data.Series("TQQQ", tqqq.dates, v))
        assert other["strategy"].cycles == runs["strategy"].cycles
        assert other["strategy"].full_spells == runs["strategy"].full_spells
        for k, want in FINAL.items():
            assert BUDGET * other[k].wealth[-1] == pytest.approx(want, rel=1e-5), k


def test_matches_old_vectorised_functions(runs, tqqq):
    """research/infinite_buy.py 의 함수와 부동소수점 수준까지 같은지."""
    sys.path.insert(0, str(ROOT / "research"))
    import infinite_buy as ib
    P = tqqq.values[None, :]
    w, cyc, expo, _ = ib.infinite_buy(P)
    assert w[0] == pytest.approx(runs["inf"].wealth[-1], rel=1e-12)
    assert cyc[0] == 72 and expo[0] == pytest.approx(runs["f"], rel=1e-12)
    assert ib.dca_hold(P)[0] == pytest.approx(runs["dca"].wealth[-1], rel=1e-12)
    assert ib.constant_mix(P, runs["f"])[0] == pytest.approx(runs["cm"].wealth[-1], rel=1e-12)
    assert np.allclose(runs["bh"].wealth, tqqq.values / tqqq.values[0], rtol=1e-12)


def test_matches_old_path_functions(runs, tqqq):
    """research/backtest_tqqq.py 의 경로 함수와 매일 자산이 같은지 (pandas 가 있을 때만)."""
    pytest.importorskip("pandas")
    sys.path.insert(0, str(ROOT / "research"))
    import backtest_tqqq as bt
    p = tqqq.values
    old = bt.path_infinite(p)
    assert np.allclose(old["wealth"], runs["inf"].wealth, rtol=1e-12)
    assert np.allclose(bt.path_dca(p), runs["dca"].wealth, rtol=1e-10)
    assert np.allclose(bt.path_constant_mix(p, runs["f"]), runs["cm"].wealth, rtol=1e-10)
    assert len(old["cycles"]) == len(runs["strategy"].cycles)
    assert old["cycles"] == runs["strategy"].cycles
