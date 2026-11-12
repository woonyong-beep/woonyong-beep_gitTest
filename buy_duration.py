"""매수듀레이션(Buy Duration) 이론 시뮬레이션.

설정
- 동일 종목, 동일 예산 B=1, 동일 투자기간 T.
- 매수듀레이션 D: 예산을 [0, D) 구간에 걸쳐 균등 분할 매수한다 (D=0 이면 일시 매수).
- 아직 매수하지 않은 현금은 무위험채권(연 r)에 둔다.
- 성과는 만기 T 시점의 총수익률 R = W_T / B - 1 의 (위험=표준편차, 기대수익률)로 평가한다.

비교 대상
- CML: t=0 에 비중 a 만큼만 일시 매수하고 나머지는 끝까지 무위험채권에 두는 정적 조합.
  (위험, 수익) 평면에서 무위험점과 일시매수점을 잇는 직선이 된다.
- 최적 매수 일정: 각 매수 시점을 하나의 "자산"으로 보고 샤프비율을 최대화하는
  매수 시점 포트폴리오(접점 포트폴리오).

실행: python buy_duration.py
"""

import numpy as np
from scipy.optimize import minimize

MONTHS = 60          # 투자기간 T = 5년 (월 단위)
DT = 1 / 12
MU, SIGMA, RF = 0.08, 0.20, 0.03   # 연 기대수익률, 변동성, 무위험이자율
N_PATHS = 200_000
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
    rng = np.random.default_rng(0)
    x = timing_assets(simulate_prices(rng, **model))
    rf_total = np.exp(RF * DT * MONTHS) - 1

    print(f"\n=== {label} ===")
    print(f"무위험 총수익률({MONTHS}개월): {rf_total:6.2%}")
    print(f"{'전략':<22}{'기대수익':>9}{'위험':>9}{'샤프':>8}{'동일위험 CML 대비':>18}")

    lump_mean, lump_std, lump_sharpe = stats(x @ duration_weights(0))
    rows = [(f"D={d:>2}개월" if d else "D= 0 (일시매수)", duration_weights(d)) for d in DURATIONS]
    w_opt = tangency_schedule(x)
    rows.append(("최적 매수일정(접점)", w_opt))

    points = []
    for name, w in rows:
        mean, std, sharpe = stats(x @ w)
        # 같은 위험을 지는 CML 위의 점 (t=0 에 일부만 일시매수) 대비 초과 기대수익
        vs_cml = mean - (rf_total + lump_sharpe * std)
        print(f"{name:<22}{mean:>9.2%}{std:>9.2%}{sharpe:>8.3f}{vs_cml:>+17.2%}")
        points.append((name, mean, std))

    top = np.argsort(w_opt)[::-1][:5]
    desc = ", ".join(f"{t}개월차 {w_opt[t]:.0%}" for t in sorted(top) if w_opt[t] > 0.01)
    print(f"최적 매수일정의 주요 매수 시점: {desc}")
    return points, (rf_total, lump_sharpe)


def plot(results, path="buy_duration_frontier.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(results), figsize=(5.5 * len(results), 4.5))
    for ax, (label, (points, (rf_total, lump_sharpe))) in zip(axes, results.items()):
        dur = points[:-1]
        stds = [p[2] for p in dur]
        ax.plot([0, max(stds) * 1.05], [rf_total, rf_total + lump_sharpe * max(stds) * 1.05],
                "--", color="gray", label="CML (lump sum + risk-free)")
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
    print(f"\n그래프 저장: {path}")


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
