"""지표 함수를 손으로 계산한 작은 예와 비교한다."""

import numpy as np
import pytest

from backtest import metrics

W = np.array([1.0, 1.1, 0.99, 1.188])     # 일별 수익률 +10%, -10%, +20%


def test_returns():
    assert np.allclose(metrics.returns(W), [0.1, -0.1, 0.2])


def test_ann_vol():
    # 편차 1/30, -1/6, 2/15 -> 분산 (1+25+16)/900/3 = 14/900 -> 표준편차 sqrt(14)/30
    assert metrics.ann_vol(W) == pytest.approx(np.sqrt(14) / 30 * np.sqrt(252))


def test_sharpe_zero_rf():
    # 평균 1/15, 연환산 (1/15)*252 / (sqrt(14)/30*sqrt(252)) = 2*sqrt(252/14) = 6*sqrt(2)
    assert metrics.sharpe(W, 0.0) == pytest.approx(6 * np.sqrt(2))


def test_sharpe_with_rf_array():
    rf = np.array([0.01, 0.01, 0.01])
    expected = (1 / 15 - 0.01) * 252 / (np.sqrt(14) / 30 * np.sqrt(252))
    assert metrics.sharpe(W, rf) == pytest.approx(expected)
    assert metrics.sharpe(W, 0.01) == pytest.approx(expected)


def test_sharpe_flat_is_nan():
    assert np.isnan(metrics.sharpe([1.0, 1.0, 1.0]))


def test_max_drawdown():
    dates = np.array(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]")
    mdd, trough, peak = metrics.max_drawdown(W, dates)
    assert mdd == pytest.approx(0.99 / 1.1 - 1)        # -10%
    assert trough == np.datetime64("2024-01-03") and peak == np.datetime64("2024-01-02")
    mdd, i, j = metrics.max_drawdown(W)
    assert (i, j) == (2, 1)


def test_max_drawdown_monotone_is_zero():
    mdd, i, _ = metrics.max_drawdown([1, 2, 3])
    assert mdd == 0 and i == 0


def test_cagr_and_final():
    dates = np.array(["2020-01-01", "2024-01-01"], dtype="datetime64[D]")   # 1461일 = 4 x 365.25
    assert metrics.years_between(dates) == 4
    assert metrics.cagr([1.0, 16.0], dates) == pytest.approx(1.0)          # 16 = 2^4
    assert metrics.cagr([2.0, 16.0], dates, initial=1.0) == pytest.approx(1.0)
    assert metrics.final_wealth([1.0, 1.5], budget=100) == pytest.approx(150)
    assert metrics.final_wealth([0.999, 1.5], initial=1.0, budget=100) == pytest.approx(150)


def test_windows_and_starts():
    w = metrics.windows([1, 2, 3, 4], 2)
    assert w.tolist() == [[1, 2, 3], [2, 3, 4]]
    assert metrics.windows([1, 2, 3, 4, 5], 2, step=2).tolist() == [[1, 2, 3], [3, 4, 5]]
    assert metrics.window_starts(["a", "b", "c", "d"], 2).tolist() == ["a", "b"]


def test_distribution():
    d = metrics.distribution([0.5, 1.0, 2.0, 1.5], budget=100)
    assert d["mean"] == pytest.approx(125)
    assert d["median"] == pytest.approx(125)
    assert d["std"] == pytest.approx(100 * np.sqrt(0.3125))
    assert d["q05"] == pytest.approx(57.5)        # 정렬 [0.5, 1, 1.5, 2], 위치 0.15 선형보간
    assert d["worst"] == pytest.approx(50) and d["worst_index"] == 0
    assert d["loss_prob"] == pytest.approx(0.25)


def test_win_rate():
    assert metrics.win_rate([1, 2, 3, 4], [2, 2, 2, 2]) == pytest.approx(0.5)
