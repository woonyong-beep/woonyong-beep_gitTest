"""무한매수법을 실제 TQQQ 일별 가격으로 백테스트하고 단순한 전략들과 비교한다.

규칙은 infinite_buy.py 의 시뮬레이션과 똑같다 (같은 함수를 그대로 가져다 쓴다).
- 무한매수법: 현재 자산을 40등분해 매 거래일 종가에 1회분씩 매수, 종가 >= 평단가 x 1.10 이면
  전량 매도 후 다음 거래일부터 새 사이클. 40회분을 다 쓰면 +10% 까지 보유 (손절 없음).
- 기준군: 0시점 전액 매수 후 보유.
- 40일 분할매수 후 보유 (익절 없음).
- 일정비중 리밸런싱: 주식 비중을 고정하고 매일 리밸런싱. 비중은 같은 구간에서 무한매수법이
  실제로 유지한 평균 주식 비중과 같게 맞춘다 (같은 노출 비교).
미투입 현금은 연 3% 고정 무위험수익률로 불어난다 (infinite_buy.RF). 실제 T-bill 금리가 아니다.
거래비용, 세금, 호가 차이는 반영하지 않았다.

데이터: data/prices/yahoo/TQQQ.csv 의 adj_close (collect.py 가 Yahoo Finance chart API 에서 직접 받은 것)
- 분할/배당 조정 종가. collect.py 가 나중에 새 행을 덧붙여도 결과가 바뀌지 않도록
  START ~ END (2010-02-11 ~ 2026-11-11, 4214행) 만 쓴다. 기간을 늘리려면 END 를 고친다.
- Yahoo 는 새 배당이 생기면 과거 조정 종가 전체에 같은 배수를 곱해 다시 맞춘다. 이 스크립트의 결과는
  모두 가격 비율로만 계산되므로 그런 상수배 재조정에는 바뀌지 않는다.
- 예전에는 공개 GitHub 저장소 culolom/culolom-backtest 의 Yahoo 사본(data/tqqq_daily.csv)을 썼는데,
  2025-12 ~ 2026-09 의 배당 조정 네 번이 날짜가 어긋나 있어 2026-11 에 이 파일로 바꿨다.
- 검증용으로 Tiingo 조정 종가 (공개 저장소 ravelab/l-etf, data/etf-tqqq.csv) 를
  data/tqqq_daily_tiingo.csv 로 저장해 두었고, 실행 시 두 소스의 일별 수익률을 비교한다.

실행 (저장소 루트에서): python research/backtest_tqqq.py
그래프는 research/backtest_tqqq.png 로 저장된다.
"""

from pathlib import Path

import numpy as np
import pandas as pd

import infinite_buy as ib
from infinite_buy import BUDGET, DT, RF, SPLITS, TAKE_PROFIT

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent           # 저장소 루트 (data/ 는 루트에 있다)
DATA = ROOT / "data" / "prices" / "yahoo" / "TQQQ.csv"
START, END = "2010-02-11", "2026-11-11"   # 발표한 수치의 기간. 파일에 이후 행이 늘어도 여기까지만 쓴다
N_ROWS = 4214
DATA_CHECK = ROOT / "data" / "tqqq_daily_tiingo.csv"
GROWTH = np.exp(RF * DT)     # 하루 무위험 성장률
HORIZONS = {"5년": 252 * 5, "1년": 252}
STEP = 1                     # 롤링 시작일 간격 (거래일)


# ---------------------------------------------------------------- 데이터

def load_prices():
    df = pd.read_csv(DATA, parse_dates=["date"])
    full = df.set_index("date")["adj_close"]
    s = full.loc[START:END]

    print("=== 데이터 점검 ===")
    print(f"파일: {DATA.relative_to(ROOT)} (adj_close, 파일 전체 {full.index[0].date()} ~ {full.index[-1].date()} "
          f"{len(full)}행 중 {START} ~ {END} 사용)")
    print(f"사용 구간: 행 수 {len(s)}  기간 {s.index[0].date()} ~ {s.index[-1].date()}")
    assert str(s.index[0].date()) == START and str(s.index[-1].date()) == END and len(s) == N_ROWS, \
        "사용 구간의 행 수나 처음/마지막 날짜가 예전과 다르다"
    assert s.index.is_monotonic_increasing and not s.index.duplicated().any(), "날짜 정렬/중복 문제"
    assert s.notna().all() and (s > 0).all(), "결측 또는 0 이하 가격"
    per_year = s.groupby(s.index.year).size()
    full = per_year.iloc[1:-1]
    print(f"연도별 거래일 수 (첫해/마지막해 제외): 최소 {full.min()}, 최대 {full.max()}  "
          f"첫해 {per_year.iloc[0]}, 마지막해 {per_year.iloc[-1]}")
    gap = s.index.to_series().diff().dt.days
    print(f"달력상 가장 긴 공백: {int(gap.max())}일 ({gap.idxmax().date()} 직전)  "
          f"5일 이상 공백 {(gap >= 5).sum()}회")
    r = s.pct_change().dropna()
    worst = r.nsmallest(3)
    print("가장 큰 일간 하락: " + ", ".join(f"{d.date()} {v:+.1%}" for d, v in worst.items()))
    # 미조정 분할(2:1 → -50%, 3:1 → -67%) 이 남아 있으면 -40% 이하 하루 낙폭이 나온다
    assert worst.iloc[0] > -0.40, "분할이 조정되지 않은 것으로 보이는 하락이 있음"

    if DATA_CHECK.exists():
        t = pd.read_csv(DATA_CHECK, parse_dates=["date"]).set_index("date")["adj_close"]
        j = pd.concat([s, t], axis=1, join="inner")
        rr = j.pct_change().dropna()
        diff = (rr.iloc[:, 0] - rr.iloc[:, 1]).abs()
        big = diff[diff > 0.001]
        print(f"교차검증 (Tiingo, 겹치는 {len(j)}일): 일별 수익률 차이 최대 {diff.max():.3%} "
              f"({diff.idxmax().date()}), 평균 {diff.mean():.5%}, 0.1% 초과 {len(big)}일"
              + (" (" + ", ".join(str(d.date()) for d in big.index) + ")" if len(big) else ""))
    return s


# ---------------------------------------------------------------- 단일 경로 (매일 자산 기록)

def path_buy_hold(p):
    return p / p[0]


def path_dca(p):
    """ib.dca_hold 와 같은 규칙: k번째 1/40 은 k일까지 무위험으로 불어난 뒤 k일 종가에 매수."""
    t = np.arange(len(p))
    k = np.arange(SPLITS)
    shares = np.exp(RF * DT * k) / p[:SPLITS] / SPLITS               # 각 회분이 사는 주식 수
    bought = k[None, :] <= t[:, None]
    stock = (bought * shares[None, :]).sum(axis=1) * p
    cash = ((~bought) / SPLITS).sum(axis=1) * np.exp(RF * DT * t)
    return stock + cash


def path_infinite(p, take_profit=TAKE_PROFIT):
    """ib.infinite_buy 의 1개 경로 버전. 매일 자산과 노출, 사이클 기록을 함께 돌려준다."""
    days = len(p) - 1
    cash, shares, cost, bought = 1.0, 0.0, 0.0, 0
    unit = cash / SPLITS
    wealth = np.empty(days + 1)
    expo = np.empty(days)
    cycles = []                 # (시작일, 매도일) 인덱스
    start = 0
    full_since = None           # 40회분을 다 쓴 날
    full_spells = []            # 40회분 소진 후 대기 구간 (소진일, 해소일)
    for t in range(days):
        s = p[t]
        if t:
            cash *= GROWTH
        sell = shares > 0 and s * shares >= (1 + take_profit) * cost
        if sell:
            cash += shares * s
            shares = cost = 0.0
            bought = 0
            unit = cash / SPLITS
            cycles.append((start, t))
            if full_since is not None:
                full_spells.append((full_since, t))
                full_since = None
            start = t + 1
        elif bought < SPLITS:
            amount = min(unit, cash)
            shares += amount / s
            cost += amount
            cash -= amount
            bought += 1
            if bought == SPLITS:
                full_since = t
        wealth[t] = cash + shares * s
        expo[t] = shares * s / wealth[t]
    cash *= GROWTH
    wealth[days] = cash + shares * p[days]
    open_cycle = (start, days) if shares > 0 else None
    if full_since is not None:
        full_spells.append((full_since, days))
    return dict(wealth=wealth, exposure=expo.mean(), expo_path=expo, cycles=cycles,
                open_cycle=open_cycle, full_spells=full_spells,
                open_pnl=(shares * p[days] / cost - 1) if shares > 0 else None)


def path_constant_mix(p, f):
    ret = p[1:] / p[:-1] - 1
    return np.concatenate([[1.0], np.cumprod(1 + f * ret + (1 - f) * (GROWTH - 1))])


def path_metrics(w, dates):
    years = (dates[-1] - dates[0]).days / 365.25
    r = w[1:] / w[:-1] - 1
    vol = r.std() * np.sqrt(252)
    sharpe = (r.mean() - (GROWTH - 1)) * 252 / vol if vol > 0 else np.nan
    dd = w / np.maximum.accumulate(w) - 1
    return dict(final=BUDGET * w[-1], cagr=w[-1] ** (1 / years) - 1, vol=vol, sharpe=sharpe,
                mdd=dd.min(), mdd_date=dates[dd.argmin()])


# ---------------------------------------------------------------- (a) 전체 기간

def full_period(s):
    p, dates = s.to_numpy(), s.index
    inf = path_infinite(p)
    f = inf["exposure"]
    curves = {
        "기준군: 0시점 전액매수": path_buy_hold(p),
        "40일 분할매수 후 보유": path_dca(p),
        "무한매수법": inf["wealth"],
        f"일정비중 {f:.0%} (동일노출)": path_constant_mix(p, f),
    }   # 일정비중 100% 는 현금이 없어 기준군과 정확히 같으므로 따로 두지 않는다
    # infinite_buy.py 의 벡터 함수와 결과가 같은지 확인 (같은 규칙인지 검증)
    P = p[None, :]
    w_ib, c_ib, e_ib, _ = ib.infinite_buy(P)
    assert np.isclose(w_ib[0], inf["wealth"][-1]) and c_ib[0] == len(inf["cycles"])
    assert np.isclose(e_ib[0], f)
    assert np.isclose(ib.dca_hold(P)[0], curves["40일 분할매수 후 보유"][-1])
    assert np.isclose(ib.constant_mix(P, f)[0], curves[f"일정비중 {f:.0%} (동일노출)"][-1])

    years = (dates[-1] - dates[0]).days / 365.25
    print(f"\n=== (a) 전체 기간 단일 경로: {dates[0].date()} ~ {dates[-1].date()} ({years:.1f}년, "
          f"{len(p) - 1}거래일), 예산 {BUDGET} ===")
    print(f"무위험수익률: 연 {RF:.0%} 고정 가정 (실제 T-bill 아님). 전액 무위험일 때 만기 자산 "
          f"{BUDGET * np.exp(RF * years):.1f}")
    print(f"{'전략':<24}{'만기자산':>12}{'CAGR':>9}{'변동성':>8}{'샤프':>7}{'최대낙폭':>8}  최대낙폭 시점")
    for name, w in curves.items():
        m = path_metrics(w, dates)
        print(f"{name:<24}{m['final']:>12,.0f}{m['cagr']:>9.1%}{m['vol']:>9.1%}{m['sharpe']:>8.2f}"
              f"{m['mdd']:>9.1%}  {m['mdd_date'].date()}")

    lens = [(e - st + 1, st, e) for st, e in inf["cycles"]]
    if inf["open_cycle"]:
        st, e = inf["open_cycle"]
        lens.append((e - st + 1, st, None))
    L, st, e = max(lens)
    end_txt = dates[e].date() if e is not None else f"{dates[-1].date()} 현재 미완료"
    spells = [(b - a, a, b) for a, b in inf["full_spells"]]
    print(f"무한매수법: 완료 사이클 {len(inf['cycles'])}회, 평균 주식 비중 {f:.1%}, "
          f"사이클 길이 중앙값 {np.median([x[0] for x in lens]):.0f}거래일")
    print(f"  가장 오래 걸린 사이클: {L}거래일 ({dates[st].date()} ~ {end_txt})")
    if spells:
        D, a, b = max(spells)
        print(f"  40회분 소진 후 +10% 까지 가장 오래 기다린 기간: {D}거래일 "
              f"({dates[a].date()} ~ {dates[b].date()}), 40회분 소진은 총 {len(spells)}번")
    if inf["open_cycle"]:
        st, _ = inf["open_cycle"]
        print(f"  마지막 날 상태: {dates[st].date()} 시작 사이클 진행 중, 평가손익 {inf['open_pnl']:+.1%}, "
              f"마지막 날 주식 비중 {inf['expo_path'][-1]:.0%}")
    return curves, f


# ---------------------------------------------------------------- (b) 모든 시작일 롤링

def windows(p, H, step=STEP):
    return np.lib.stride_tricks.sliding_window_view(p, H + 1)[::step]


def rolling(s, H, label, f_full):
    p, dates = s.to_numpy(), s.index
    P = windows(p, H)
    starts = dates[: len(p) - H][::STEP]
    w_ib, cyc, expo, stuck = ib.infinite_buy(P)
    res = {
        "기준군: 0시점 전액매수": P[:, -1] / P[:, 0],
        "40일 분할매수 후 보유": ib.dca_hold(P),
        "무한매수법": w_ib,
        "일정비중 (창별 동일노출)": ib.constant_mix(P, expo[:, None]),
        f"일정비중 {f_full:.0%} 고정": ib.constant_mix(P, f_full),
    }
    n = len(P)
    span = (dates[-1] - dates[0]).days / 365.25
    print(f"\n=== (b) {label} 보유, 시작일 {n}개 ({starts[0].date()} ~ {starts[-1].date()}, "
          f"{STEP}거래일 간격) ===")
    print(f"주의: 구간이 서로 겹쳐 독립 표본이 아니다. 겹치지 않는 구간은 약 {span * 252 / H:.1f}개뿐이다. "
          f"전액 무위험이면 {BUDGET * np.exp(RF * H * DT):.1f}")
    print(f"{'전략':<24}{'평균':>8}{'중앙값':>8}{'표준편차':>7}{'하위5%':>8}{'최악':>7}  최악 시작일 {'손실확률':>5}")
    for name, w in res.items():
        i = w.argmin()
        print(f"{name:<24}{BUDGET * w.mean():>9.1f}{BUDGET * np.median(w):>9.1f}{BUDGET * w.std():>9.1f}"
              f"{BUDGET * np.quantile(w, 0.05):>9.1f}{BUDGET * w[i]:>9.1f}  {starts[i].date()}"
              f"{(w < 1).mean():>9.1%}")
    names = list(res)
    print(f"무한매수법이 더 나은 시작일 비율: 기준군 대비 {(w_ib > res[names[0]]).mean():.1%}, "
          f"분할매수 후 보유 대비 {(w_ib > res[names[1]]).mean():.1%}, "
          f"창별 동일노출 일정비중 대비 {(w_ib > res[names[3]]).mean():.1%}, "
          f"{f_full:.0%} 고정 일정비중 대비 {(w_ib > res[names[4]]).mean():.1%}")
    print(f"무한매수법: 평균 완료 사이클 {cyc.mean():.1f}회, 평균 주식 비중 {expo.mean():.1%} "
          f"(창별 범위 {expo.min():.0%}~{expo.max():.0%}), 만기에 평가손 상태로 물린 시작일 {stuck.mean():.1%}")
    return res, starts


# ---------------------------------------------------------------- (c) 큰 하락 직전 시작

def drawdown_episodes(s, threshold=-0.45):
    """고점 대비 threshold 이상 빠진 하락 구간: (고점일, 저점일, 낙폭)."""
    p = s.to_numpy()
    eps, peak_i, i = [], 0, 0
    while i < len(p):
        if p[i] >= p[peak_i]:
            peak_i = i
        elif p[i] / p[peak_i] - 1 <= threshold:
            j = i
            trough = i
            while j < len(p) and p[j] < p[peak_i]:
                if p[j] < p[trough]:
                    trough = j
                j += 1
            eps.append((s.index[peak_i], s.index[trough], p[trough] / p[peak_i] - 1))
            peak_i = i = j
            continue
        i += 1
    return eps


def window_row(s, start, H):
    """start 일부터 H 거래일 (데이터가 모자라면 마지막 날까지) 각 전략 결과."""
    i0 = s.index.searchsorted(start)
    p = s.to_numpy()[i0: i0 + H + 1]
    inf = path_infinite(p)
    first = inf["cycles"][0][1] - inf["cycles"][0][0] + 1 if inf["cycles"] else None
    return dict(
        start=s.index[i0].date(), end=s.index[i0 + len(p) - 1].date(), full=len(p) == H + 1,
        bh=BUDGET * p[-1] / p[0], dca=BUDGET * path_dca(p)[-1], ib=BUDGET * inf["wealth"][-1],
        cm=BUDGET * path_constant_mix(p, inf["exposure"])[-1], expo=inf["exposure"],
        cycles=len(inf["cycles"]), first=first, stuck=inf["open_pnl"],
        ib_mdd=(inf["wealth"] / np.maximum.accumulate(inf["wealth"]) - 1).min(),
        bh_mdd=(p / np.maximum.accumulate(p) - 1).min())


def print_rows(rows):
    print(f"{'시작일':<11}{'종료일':<11}{'기준군':>7}{'분할보유':>8}{'무한매수':>8}{'동일노출':>8}"
          f"{'비중':>6}{'사이클':>5}{'첫익절':>6}{'만기평가손익':>8}{'무한MDD':>8}{'기준MDD':>8}")
    for r in rows:
        first = f"{r['first']}일" if r["first"] else "없음"
        stuck = f"{r['stuck']:+.0%}" if r["stuck"] is not None else "-"
        mark = "" if r["full"] else " *"
        print(f"{str(r['start']):<11}{str(r['end']) + mark:<11}{r['bh']:>9.1f}{r['dca']:>10.1f}"
              f"{r['ib']:>10.1f}{r['cm']:>10.1f}{r['expo']:>8.0%}{r['cycles']:>7}{first:>8}"
              f"{stuck:>10}{r['ib_mdd']:>10.0%}{r['bh_mdd']:>9.0%}")


def crash_windows(s):
    eps = drawdown_episodes(s)
    print("\n=== (c) 큰 하락(고점 대비 -45% 이상) 고점에서 시작한 경우 ===")
    print("하락 구간: " + "; ".join(f"{a.date()} 고점 → {b.date()} 저점 {d:+.0%}" for a, b, d in eps))
    print("비중 = 무한매수법 평균 주식 비중 (동일노출 일정비중에 사용), 첫익절 = 첫 사이클 완료까지 거래일, "
          "만기평가손익 = 마지막 날 진행 중 사이클의 평단 대비 손익, * = 데이터 끝에서 잘린 구간")
    for label, H in HORIZONS.items():
        print(f"\n[{label} 보유, 각 하락의 고점일에 시작]")
        print_rows([window_row(s, a, H) for a, _, _ in eps])
    print("\n[2021~2022 하락장 전후 매월 첫 거래일 시작, 1년 보유]")
    months = pd.date_range("2021-07-01", "2022-06-01", freq="MS")
    print_rows([window_row(s, m, 252) for m in months])
    print("\n[같은 시작일, 데이터 마지막 날까지 보유]")
    print_rows([window_row(s, m, 10**6) for m in months])


# ---------------------------------------------------------------- 그래프

def plot(s, curves, path=HERE / "backtest_tqqq.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names_en = ["Buy & hold (day 0)", "40-day DCA, then hold", "Infinite buying (40 splits, +10% TP)", None]
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for (name, w), en, c in zip(curves.items(), names_en, colors):
        if en is None:
            en = f"Constant mix {name.split()[1]} (same exposure)"
        ax.plot(s.index, BUDGET * w, color=c, lw=2, label=f"{en}: {BUDGET * w[-1]:,.0f}")
    rf = BUDGET * np.exp(RF * (s.index - s.index[0]).days / 365.25)
    ax.plot(s.index, rf, color="#8a8984", lw=1.5, ls="--", label=f"Risk-free {RF:.0%}/yr (assumed): {rf[-1]:,.0f}")
    ax.set_yscale("log")
    ax.set_ylabel("Wealth (start = 100, log scale)", color="#52514e")
    ax.set_title(f"TQQQ backtest {s.index[0].date()} to {s.index[-1].date()} (adjusted close)",
                 color="#0b0b0b", loc="left")
    ax.grid(True, which="major", color="#e6e5e0", lw=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#b5b4ad")
    ax.tick_params(colors="#52514e")
    ax.legend(frameon=False, loc="upper left", fontsize=9, title="Final wealth (start = 100)", title_fontsize=9)
    ax.margins(x=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"\n그래프 저장: {path.name}")


if __name__ == "__main__":
    s = load_prices()
    curves, f_full = full_period(s)
    for label, H in HORIZONS.items():
        rolling(s, H, label, f_full)
    crash_windows(s)
    plot(s, curves)
