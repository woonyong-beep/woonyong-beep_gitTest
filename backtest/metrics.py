"""성과 지표와 롤링 시작일 분포 도구.

정의 (research/backtest_tqqq.py 의 path_metrics 와 같다)
- 기간(년) = (마지막 날 - 첫날) 달력일 / 365.25
- CAGR = (최종 / 시작) ** (1 / 기간) - 1. 시작 = 초기 자본 (지정 안 하면 wealth[0])
- 연 변동성 = 일별 수익률의 표준편차 (모표준편차, ddof=0) x sqrt(252)
- 샤프 = (일별 수익률 평균 - 일별 무위험 수익률 평균) x 252 / 연 변동성
- 최대낙폭 = min(wealth / 그때까지 최고값 - 1), 그 날짜
"""

import numpy as np

PERIODS = 252


def returns(wealth):
    w = np.asarray(wealth, float)
    return w[1:] / w[:-1] - 1


def years_between(dates):
    d = np.asarray(dates, dtype="datetime64[D]")
    return (d[-1] - d[0]).astype(int) / 365.25


def final_wealth(wealth, initial=None, budget=1.0):
    """초기 자본을 budget 으로 맞췄을 때의 최종 자산."""
    w = np.asarray(wealth, float)
    base = w[0] if initial is None else initial
    return budget * w[-1] / base


def cagr(wealth, dates, initial=None):
    w = np.asarray(wealth, float)
    base = w[0] if initial is None else initial
    return (w[-1] / base) ** (1 / years_between(dates)) - 1


def ann_vol(wealth, periods=PERIODS):
    return returns(wealth).std() * np.sqrt(periods)


def sharpe(wealth, rf_returns=0.0, periods=PERIODS):
    """rf_returns: 기간별 무위험 수익률 (숫자 하나 또는 len(wealth)-1 길이 배열)."""
    r = returns(wealth)
    vol = r.std() * np.sqrt(periods)
    if vol == 0:
        return np.nan
    return (r.mean() - np.mean(rf_returns)) * periods / vol


def max_drawdown(wealth, dates=None):
    """(최대낙폭, 저점 날짜 또는 인덱스, 직전 고점 날짜 또는 인덱스)."""
    w = np.asarray(wealth, float)
    peak = np.maximum.accumulate(w)
    dd = w / peak - 1
    i = int(dd.argmin())
    j = int(np.argmax(w[: i + 1] == peak[i]))
    if dates is None:
        return dd[i], i, j
    return dd[i], dates[i], dates[j]


def summary(result, budget=1.0):
    """engine.Result 하나의 지표 dict."""
    w, d = result.wealth, result.dates
    mdd, mdd_date, peak_date = max_drawdown(w, d)
    return dict(final=final_wealth(w, result.initial, budget), cagr=cagr(w, d, result.initial),
                vol=ann_vol(w), sharpe=sharpe(w, result.rf_returns), mdd=mdd, mdd_date=mdd_date,
                peak_date=peak_date, exposure=result.exposure, cost=result.total_cost)


def format_summary(name, m, budget=1.0):
    return (f"{name:<24}{m['final']:>12,.0f}{m['cagr']:>9.1%}{m['vol']:>9.1%}{m['sharpe']:>8.2f}"
            f"{m['mdd']:>9.1%}  {m['mdd_date']}")


# ---------------------------------------------------------------- 롤링 시작일 (research/backtest_tqqq.py (b))

def windows(prices, horizon, step=1):
    """길이 horizon+1 의 겹치는 창들 (시작일을 step 거래일 간격으로). shape (창 수, horizon+1)."""
    return np.lib.stride_tricks.sliding_window_view(np.asarray(prices, float), horizon + 1)[::step]


def window_starts(dates, horizon, step=1):
    return np.asarray(dates)[: len(dates) - horizon][::step]


def distribution(w, budget=1.0):
    """창별 최종 자산(예산 1 기준) 배열의 분포: 평균, 중앙값, 표준편차, 하위 5%, 최악(과 그 위치), 손실확률."""
    w = np.asarray(w, float)
    i = int(w.argmin())
    return dict(mean=budget * w.mean(), median=budget * np.median(w), std=budget * w.std(),
                q05=budget * np.quantile(w, 0.05), worst=budget * w[i], worst_index=i,
                loss_prob=(w < 1).mean())


def win_rate(a, b):
    """a 가 b 보다 큰 창의 비율."""
    return (np.asarray(a) > np.asarray(b)).mean()


def rolling_run(make_strategy, series, horizon, step=1, **run_kwargs):
    """엔진으로 시작일마다 따로 돌린 최종 자산 배열 (예산 1 기준)과 시작일.

    make_strategy: 인자 없이 새 전략 객체를 만드는 함수. 창이 많으면 느리다 (창 수 x horizon 번 반복).
    """
    from backtest.data import Series
    from backtest.engine import run
    starts = list(range(0, len(series) - horizon, step))
    out = np.empty(len(starts))
    for k, i in enumerate(starts):
        sub = Series(series.name, series.dates[i: i + horizon + 1], series.values[i: i + horizon + 1])
        r = run(make_strategy(), sub, **run_kwargs)
        out[k] = r.wealth[-1] / r.initial
    return out, series.dates[starts]
