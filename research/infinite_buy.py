"""무한매수법(분할매수 + 10% 익절 + 반복) 시뮬레이션.

단순화한 규칙
- 현재 자산을 40등분해 매 거래일 1회분씩 매수한다. 미투입 현금은 무위험채권에 둔다.
- 종가가 평단가의 +10% 이상이면 전량 매도하고, 다음 거래일부터 새 사이클을 시작한다.
- 40회분을 모두 소진하면 +10% 에 도달할 때까지 보유한다 (손절 없음).
- 실제 무한매수법의 LOC 주문, 절반 평단 매수, 쿼터 손절 등 세부 규칙은 반영하지 않았다.

비교 대상
- 기준군: 0시점 전액 매수 후 보유.
- 40일 분할매수 후 보유 (익절 없음): 익절 규칙의 효과만 분리해 보기 위함.
- 일정비중 리밸런싱: 주식 비중을 고정하고 매일 리밸런싱하는 전략 중
  무한매수법과 기대 만기자산이 같은 것. 같은 기대수익을 더 단순하게 얻는 방법과의 비교다.

실행 (저장소 루트에서): python research/infinite_buy.py
"""

import numpy as np

YEARS = 5
DAYS = 252 * YEARS
DT = 1 / 252
RF = 0.03
BUDGET = 100
N_PATHS = 100_000
SPLITS = 40
TAKE_PROFIT = 0.10


def simulate_prices(rng, mu, sigma, kappa=0.0):
    """일별 가격 경로. kappa > 0 이면 로그가격이 추세선 주위로 평균회귀한다."""
    eps = rng.standard_normal((N_PATHS, DAYS)) * sigma * np.sqrt(DT)
    phi = np.exp(-kappa * DT)
    x = np.zeros((N_PATHS, DAYS + 1))
    for t in range(DAYS):
        x[:, t + 1] = phi * x[:, t] + eps[:, t]
    return np.exp((mu - 0.5 * sigma**2) * DT * np.arange(DAYS + 1) + x)


def infinite_buy(prices, take_profit=TAKE_PROFIT):
    """만기 자산(예산 1 기준), 완료 사이클 수, 평균 주식 비중, 만기 시 물린 상태 여부."""
    n, days = prices.shape[0], prices.shape[1] - 1   # 기간은 가격 배열 길이에서 정한다 (실데이터 백테스트에서도 재사용)
    cash = np.ones(n)
    shares = np.zeros(n)
    cost = np.zeros(n)            # 현재 사이클 투입 원금
    bought = np.zeros(n, int)     # 현재 사이클 매수 횟수
    unit = cash / SPLITS          # 1회 매수 금액
    cycles = np.zeros(n)
    exposure = np.zeros(n)
    growth = np.exp(RF * DT)

    for t in range(days):
        s = prices[:, t]
        if t:
            cash *= growth
        sell = (shares > 0) & (s * shares >= (1 + take_profit) * cost)
        cash[sell] += shares[sell] * s[sell]
        shares[sell] = cost[sell] = 0
        bought[sell] = 0
        unit[sell] = cash[sell] / SPLITS
        cycles += sell

        buy = (bought < SPLITS) & ~sell
        amount = np.where(buy, np.minimum(unit, cash), 0)
        shares += amount / s
        cost += amount
        cash -= amount
        bought += buy
        exposure += shares * s / (cash + shares * s)

    s = prices[:, -1]
    cash *= growth
    wealth = cash + shares * s
    stuck = (shares > 0) & (s * shares < cost)
    return wealth, cycles, exposure / days, stuck


def dca_hold(prices):
    """40일 분할매수 후 만기까지 보유 (익절 없음)."""
    t = np.arange(SPLITS)
    return (np.exp(RF * DT * t) * prices[:, -1:] / prices[:, :SPLITS]).mean(axis=1)


def constant_mix(prices, f):
    """주식 비중을 f 로 매일 리밸런싱하는 전략의 만기 자산."""
    ret = prices[:, 1:] / prices[:, :-1] - 1
    return np.exp(np.log1p(f * ret + (1 - f) * (np.exp(RF * DT) - 1)).sum(axis=1))


def matched_constant_mix(prices, target_mean):
    """기대 만기자산이 target_mean 과 같아지는 일정비중 전략을 찾는다."""
    lo, hi = 0.0, 1.0
    for _ in range(20):
        mid = (lo + hi) / 2
        if constant_mix(prices, mid).mean() < target_mean:
            lo = mid
        else:
            hi = mid
    return mid, constant_mix(prices, mid)


def describe(name, wealth, rf_total):
    r = wealth - 1
    mean, std = r.mean(), r.std()
    growth = np.log(wealth).mean() / YEARS      # 연 기대 로그성장률 (복리 기준 성장 속도)
    print(f"{name:<26}{BUDGET * (1 + mean):>9.1f}{BUDGET * std:>8.1f}{(mean - rf_total) / std:>8.3f}"
          f"{BUDGET * np.median(wealth):>9.1f}{growth:>9.2%}{(wealth < 1).mean():>9.1%}"
          f"{BUDGET * np.quantile(wealth, 0.05):>9.1f}")


def run(label, mu, sigma, kappa=0.0):
    prices = simulate_prices(np.random.default_rng(0), mu, sigma, kappa)
    rf_total = np.exp(RF * YEARS) - 1

    print(f"\n=== {label} (연 기대수익 {mu:.0%}, 변동성 {sigma:.0%}) ===")
    print(f"{'전략':<26}{'기대자산':>6}{'위험':>7}{'샤프':>7}{'중앙값':>7}{'로그성장률':>6}{'손실확률':>6}{'하위5%':>8}")
    describe("기준군: 0시점 전액매수", prices[:, -1] / prices[:, 0], rf_total)
    describe("40일 분할매수 후 보유", dca_hold(prices), rf_total)
    wealth, cycles, exposure, stuck = infinite_buy(prices)
    describe("무한매수법", wealth, rf_total)
    f, mix = matched_constant_mix(prices, wealth.mean())
    describe(f"일정비중 {f:.0%} 리밸런싱", mix, rf_total)
    print(f"무한매수법: 평균 완료 사이클 {cycles.mean():.1f}회, 평균 주식 비중 {exposure.mean():.0%}, "
          f"만기에 평가손 상태로 물려 있는 경로 {stuck.mean():.1%}")


if __name__ == "__main__":
    run("시장포트폴리오, 랜덤워크", 0.08, 0.16)
    # 3배 레버리지: 기대수익 = 무위험 + 3 x 시장위험프리미엄, 변동성 = 3 x 시장 변동성
    run("3배 레버리지, 랜덤워크", RF + 3 * 0.05, 3 * 0.16)
    run("3배 레버리지, 평균회귀", RF + 3 * 0.05, 3 * 0.16, kappa=0.5)
