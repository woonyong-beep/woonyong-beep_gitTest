"""매수듀레이션(Buy Duration) 이론 시뮬레이션.

설정
- 동일 종목, 동일 예산 100, 동일 투자기간 T.
- 투자종목은 시장포트폴리오의 기대수익률과 변동성을 따른다.
  따라서 기준군과 무위험채권을 잇는 선이 곧 자본시장선(CML)이다.
- 기준군: 0시점에 예산 100 전액 매수.
- 비교군: 그 외의 매수 일정. 아직 매수하지 않은 예산은 무위험채권에 둔다.
- 매수듀레이션 D: 예산을 [0, D) 구간에 걸쳐 균등 분할 매수한다 (D=0 이면 일시 매수).
- 성과는 만기 T 시점의 총수익률 R = W_T / B - 1 의 (위험=표준편차, 기대수익률)로 평가한다.

비교 대상
- CML: t=0 에 비중 a 만큼만 일시 매수하고 나머지는 끝까지 무위험채권에 두는 정적 조합.
  (위험, 수익) 평면에서 무위험점과 일시매수점을 잇는 직선이 된다.
- 최적 매수 일정: 각 매수 시점을 하나의 "자산"으로 보고 샤프비율을 최대화하는
  매수 시점 포트폴리오(접점 포트폴리오).

실행 (저장소 루트에서): python research/buy_duration.py
그래프는 research/buy_duration_frontier.png 로 저장된다.
"""

from pathlib import Path

import numpy as np
from scipy.optimize import minimize

MONTHS = 60          # 투자기간 T = 5년 (월 단위)
DT = 1 / 12
# 투자종목 = 시장포트폴리오. 기대수익률과 변동성은 시장포트폴리오의 값을 적용한다.
# (가정: 무위험 3%, 시장위험프리미엄 5%, 시장 변동성 16% -> 연 샤프비율 약 0.31)
RF = 0.03                  # 무위험이자율 (연)
MU, SIGMA = 0.08, 0.16     # 시장포트폴리오 기대수익률, 변동성 (연)
N_PATHS = 200_000
BUDGET = 100       # 예산
DURATIONS = [0, 6, 12, 24, 36, 48, 60]   # 매수듀레이션 (개월). 0 = 일시 매수


def simulate_prices(rng, kappa=0.0, x0=0.0):
    """월별 가격 경로 S_0..S_T (S_0 = 1 로 정규화).

    kappa = 0  : 기하 브라운 운동 (랜덤워크, 예측 불가).
    kappa > 0  : 로그가격이 추세선 주위로 평균회귀 (연 회귀속도 kappa).
    x0         : 시작 시점의 추세 대비 괴리 (x0 > 0 이면 고평가 상태에서 시작).
    """
    eps = rng.standard_normal((N_PATHS, MONTHS)) * SIGMA * np.sqrt(DT)
    phi = np.exp(-kappa * DT)
    x = np.empty((N_PATHS, MONTHS + 1))
    x[:, 0] = x0
    for t in range(MONTHS):
        x[:, t + 1] = phi * x[:, t] + eps[:, t]
    trend = (MU - 0.5 * SIGMA**2) * DT * np.arange(MONTHS + 1)
    return np.exp(trend + x - x0)


def timing_assets(prices):
    """'t 시점에 1원을 매수' 하는 전략 각각의 만기 가치 X_t.

    X_t = (t 까지 무위험채권으로 불린 현금) * (t 에 사서 T 까지 보유한 주식 수익).
    모든 매수 일정은 X_0..X_{T-1} 과 무위험채권의 포트폴리오다.
    """
    t = np.arange(MONTHS)
    return np.exp(RF * DT * t) * prices[:, -1:] / prices[:, :-1]


def duration_weights(d):
    w = np.zeros(MONTHS)
    w[: max(d, 1)] = 1 / max(d, 1)
    return w


def stats(wealth):
    """wealth: 예산 1 기준 만기 자산. (기대수익률, 위험, 샤프)를 돌려준다."""
    rf_total = np.exp(RF * DT * MONTHS) - 1
    r = wealth - 1
    mean, std = r.mean(), r.std()
    return mean, std, (mean - rf_total) / std


def tangency_schedule(x):
    """매수 시점 자산 X_t 들로 만든 롱온리 최대 샤프 포트폴리오."""
    rf_gross = np.exp(RF * DT * MONTHS)
    excess = x.mean(axis=0) - rf_gross
    cov = np.cov(x, rowvar=False)

    def neg_sharpe(w):
        return -(w @ excess) / np.sqrt(w @ cov @ w)

    best = None
    for start in (np.full(MONTHS, 1 / MONTHS), duration_weights(0), duration_weights(12)[::-1]):
        res = minimize(neg_sharpe, start, method="SLSQP",
                       bounds=[(0, 1)] * MONTHS,
                       constraints={"type": "eq", "fun": lambda w: w.sum() - 1})
        if best is None or res.fun < best.fun:
            best = res
    return best.x


def run(label, **model):
    """기준군(0시점에 예산 전액 매수)과 비교군(분할 매수 + 잔여 예산은 무위험채권)을 비교."""
    rng = np.random.default_rng(0)
    x = timing_assets(simulate_prices(rng, **model))
    rf_total = np.exp(RF * DT * MONTHS) - 1

    print(f"\n=== {label} ===")
    print(f"예산 {BUDGET}, 전액 무위험채권일 때 만기 자산: {BUDGET * (1 + rf_total):.1f}")
    print(f"{'전략':<22}{'기대만기자산':>8}{'위험':>8}{'샤프':>8}"
          f"{'기준군 대비':>10}{'기준군 이길 확률':>12}{'위험조정 초과':>10}")

    base = x @ duration_weights(0)          # 기준군: 0시점 전액 매수
    base_mean, base_std, base_sharpe = stats(base)
    rows = [("기준군: 0시점 전액매수", duration_weights(0))]
    rows += [(f"비교군: D={d:>2}개월", duration_weights(d)) for d in DURATIONS[1:]]
    w_opt = tangency_schedule(x)
    rows.append(("비교군: 최적 매수일정", w_opt))

    points = []
    for name, w in rows:
        wealth = x @ w
        mean, std, sharpe = stats(wealth)
        diff = BUDGET * (mean - base_mean)                  # 기대 만기자산 차이
        win = (wealth > base).mean()                        # 기준군보다 만기자산이 큰 경로 비율
        # 같은 위험을 지도록 기준군을 무위험채권과 섞었을 때 대비 초과 기대자산
        adj = BUDGET * (mean - (rf_total + base_sharpe * std))
        print(f"{name:<22}{BUDGET * (1 + mean):>12.1f}{BUDGET * std:>10.1f}{sharpe:>10.3f}"
              f"{diff:>+13.1f}{win:>17.1%}{adj:>+15.1f}")
        points.append((name, mean, std))

    top = np.argsort(w_opt)[::-1][:5]
    desc = ", ".join(f"{t}개월차 {w_opt[t]:.0%}" for t in sorted(top) if w_opt[t] > 0.01)
    print(f"최적 매수일정의 주요 매수 시점: {desc}")
    return points, (rf_total, base_sharpe)


def plot(results, path=Path(__file__).resolve().parent / "buy_duration_frontier.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(results), figsize=(5.5 * len(results), 4.5))
    for ax, (label, (points, (rf_total, lump_sharpe))) in zip(axes, results.items()):
        dur = points[:-1]
        stds = [p[2] for p in dur]
        ax.plot([0, max(stds) * 1.05], [rf_total, rf_total + lump_sharpe * max(stds) * 1.05],
                "--", color="gray", label="CML (market lump sum at t=0 + risk-free)")
        ax.plot(stds, [p[1] for p in dur], "o-", label="buy-duration frontier")
        for d, p in zip(DURATIONS, dur):
            ax.annotate(f"D={d}", (p[2], p[1]), textcoords="offset points", xytext=(5, -10), fontsize=8)
        ax.plot(points[-1][2], points[-1][1], "r*", markersize=14, label="optimal schedule")
        ax.set_title(label)
        ax.set_xlabel("risk (std of total return)")
        ax.set_ylabel("expected total return")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"\n그래프 저장: {path.name}")


if __name__ == "__main__":
    scenarios = {
        "Random walk (GBM)": dict(kappa=0.0),
        "Mean reversion, fair start": dict(kappa=0.5),
        "Mean reversion, +20% overvalued start": dict(kappa=0.5, x0=0.2),
    }
    korean = ["랜덤워크 (예측 불가)", "평균회귀, 적정가에서 시작", "평균회귀, 20% 고평가에서 시작"]
    results = {}
    for (label, model), ko in zip(scenarios.items(), korean):
        results[label] = run(ko, **model)
    plot(results)
