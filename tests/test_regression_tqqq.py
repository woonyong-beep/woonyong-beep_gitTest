"""새 엔진이 research/backtest_tqqq.py (a) 의 TQQQ 수치를 그대로 재현하는지 확인한다.

데이터는 예전 스크립트와 같은 data/tqqq_daily.csv (2010-02-11 ~ 2026-11-11, 4214행) 를 쓴다.
기대값 (research/backtest_tqqq.py 출력, 예산 100):
  기준군 29,238 / 40일 분할매수 후 보유 24,239 / 무한매수법 23,480 / 일정비중 70% 12,212
  완료 사이클 72회, 평균 주식 비중 70.1%, 가장 오래 걸린 사이클 780거래일 (2021-11-01 ~ 2024-12-06)
"""

import sys

import numpy as np
import pytest

from backtest import data, engine, metrics
from backtest.strategies import BuyAndHold, ConstantWeight, InfiniteBuy, SplitBuy
from tests.conftest import ROOT

RF = 0.03
BUDGET = 100


@pytest.fixture(scope="module")
def tqqq():
    return data.load_csv(ROOT / "data" / "tqqq_daily.csv", name="TQQQ")


@pytest.fixture(scope="module")
def runs(tqqq):
    inf = InfiniteBuy("TQQQ", splits=40, take_profit=0.10)
    r_inf = engine.run(inf, tqqq, rf=RF)
    f = r_inf.exposure
    return dict(
        bh=engine.run(BuyAndHold("TQQQ"), tqqq, rf=RF),
        dca=engine.run(SplitBuy("TQQQ", splits=40), tqqq, rf=RF),
        inf=r_inf,
        cm=engine.run(ConstantWeight({"TQQQ": f}), tqqq, rf=RF),
        strategy=inf, f=f)


def test_data_is_the_old_file(tqqq):
    assert len(tqqq) == 4214
    assert str(tqqq.dates[0]) == "2010-02-11" and str(tqqq.dates[-1]) == "2026-11-11"


def test_final_wealth(runs):
    got = {k: round(BUDGET * runs[k].wealth[-1]) for k in ("bh", "dca", "inf", "cm")}
    assert got == {"bh": 29238, "dca": 24239, "inf": 23480, "cm": 12212}


def test_infinite_buy_cycles_and_exposure(runs, tqqq):
    s = runs["strategy"]
    assert len(s.cycles) == 72
    assert round(runs["f"], 3) == 0.701
    L, a, b = max(s.cycle_lengths(len(tqqq)))
    assert L == 780
    assert str(tqqq.dates[a]) == "2021-11-01" and str(tqqq.dates[b]) == "2024-12-06"
    D, a, b = max((b - a, a, b) for a, b in s.full_spells)
    assert (D, len(s.full_spells)) == (740, 31)


def test_metrics_table(runs):
    # research/backtest_tqqq.py (a) 표의 CAGR, 변동성, 샤프, 최대낙폭
    expected = {"bh": (0.404, 0.613, 0.82, -0.817), "dca": (0.388, 0.613, 0.80, -0.817),
                "inf": (0.385, 0.489, 0.85, -0.811), "cm": (0.332, 0.430, 0.82, -0.659)}
    for k, (cagr, vol, sh, mdd) in expected.items():
        m = metrics.summary(runs[k], budget=BUDGET)
        assert (round(m["cagr"], 3), round(m["vol"], 3), round(m["sharpe"], 2), round(m["mdd"], 3)) == \
            (cagr, vol, sh, mdd), k
        assert str(m["mdd_date"]) == "2022-12-28"


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
