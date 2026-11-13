/* 계산 로직. 저장소의 Python 스크립트를 그대로 옮긴 것이다.
 *  - 매수듀레이션 몬테카를로: buy_duration.py (simulate_prices, timing_assets, duration_weights, stats, run)
 *  - 무한매수법 백테스트:    backtest_tqqq.py (a) (path_buy_hold, path_dca, path_infinite,
 *                             path_constant_mix, path_metrics) 와 infinite_buy.py 의 규칙
 * 브라우저에서는 window.Calc, Node 에서는 module.exports 로 쓴다 (검증 스크립트용).
 */
(function (root) {
  "use strict";

  // ------------------------------------------------------------ 난수 (시드 고정)
  // xoshiro128** + splitmix32 시드 확장, 정규분포는 Box-Muller (두 값을 모두 사용).
  function makeRng(seed) {
    let s = seed >>> 0;
    function splitmix() {
      s = (s + 0x9e3779b9) >>> 0;
      let z = s;
      z = Math.imul(z ^ (z >>> 16), 0x85ebca6b) >>> 0;
      z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35) >>> 0;
      return (z ^ (z >>> 16)) >>> 0;
    }
    let a = splitmix(), b = splitmix(), c = splitmix(), d = splitmix();
    function next() {           // [0, 1) 균등분포
      const r = Math.imul(rotl(Math.imul(b, 5), 7), 9) >>> 0;
      const t = (b << 9) >>> 0;
      c ^= a; d ^= b; b ^= c; a ^= d; c ^= t;
      d = rotl(d, 11);
      return r / 4294967296;
    }
    function rotl(x, k) { return ((x << k) | (x >>> (32 - k))) >>> 0; }
    let spare = null;
    function normal() {
      if (spare !== null) { const v = spare; spare = null; return v; }
      let u = 0;
      while (u === 0) u = next();
      const v = next();
      const r = Math.sqrt(-2 * Math.log(u));
      spare = r * Math.sin(2 * Math.PI * v);
      return r * Math.cos(2 * Math.PI * v);
    }
    return { next, normal };
  }

  // ------------------------------------------------------------ 1. 매수듀레이션
  const BUDGET = 100;
  const BASE_DURATIONS = [0, 6, 12, 24, 36, 48, 60];

  /** 투자기간(개월)에 맞춰 자른 듀레이션 목록. 기간보다 긴 것은 빼고, 기간 전체(D=M)는 항상 넣는다. */
  function durationsFor(months) {
    const ds = BASE_DURATIONS.filter((d) => d < months);
    ds.push(months);
    return ds;
  }

  /**
   * 몬테카를로 상태 객체를 만든다. step(n) 으로 n개 경로씩 나눠 돌리고 result() 로 표를 얻는다.
   * p = { mu, sigma, rf, years, kappa, x0, paths, seed }
   * buy_duration.py 와 같은 정의:
   *   로그가격 x_{t+1} = phi x_t + eps_t (phi = exp(-kappa dt), x_0 = x0),
   *   S_t = exp((mu - sigma^2/2) dt t + x_t - x0),
   *   X_t = exp(rf dt t) S_T / S_t  ("t 시점에 1원 매수" 의 만기 가치),
   *   D 개월 분할매수 = X_0..X_{max(D,1)-1} 의 균등 평균.
   */
  function durationSim(p) {
    const M = Math.max(1, Math.round(p.years * 12));
    const DT = 1 / 12;
    const ds = durationsFor(M);
    const K = ds.length;
    const rng = makeRng(p.seed);
    const phi = Math.exp(-p.kappa * DT);
    const sd = p.sigma * Math.sqrt(DT);
    const drift = (p.mu - 0.5 * p.sigma * p.sigma) * DT;
    const logS = new Float64Array(M + 1);
    const cum = new Float64Array(M + 1);           // X 의 누적합
    const sum = new Float64Array(K), sumsq = new Float64Array(K), win = new Float64Array(K);
    const rfLog = p.rf * DT;
    let done = 0;

    function step(n) {
      const end = Math.min(p.paths, done + n);
      for (let i = done; i < end; i++) {
        let x = p.x0;
        logS[0] = 0;
        for (let t = 0; t < M; t++) {
          x = phi * x + rng.normal() * sd;
          logS[t + 1] = drift * (t + 1) + x - p.x0;
        }
        const lT = logS[M];
        cum[0] = 0;
        for (let t = 0; t < M; t++) cum[t + 1] = cum[t] + Math.exp(rfLog * t + lT - logS[t]);
        const base = cum[1];
        for (let k = 0; k < K; k++) {
          const m = Math.max(ds[k], 1);
          const w = cum[m] / m;
          const r = w - 1;
          sum[k] += r;
          sumsq[k] += r * r;
          if (w > base) win[k] += 1;
        }
      }
      done = end;
      return done;
    }

    function result() {
      const rfTotal = Math.exp(p.rf * DT * M) - 1;
      const st = ds.map((d, k) => {
        const mean = sum[k] / done;
        const std = Math.sqrt(Math.max(0, sumsq[k] / done - mean * mean));
        return { d, mean, std, sharpe: (mean - rfTotal) / std, win: win[k] / done };
      });
      const b = st[0];
      const rows = st.map((s, k) => ({
        name: k === 0 ? "기준군: 0시점 전액매수" : `비교군: D=${s.d}개월`,
        d: s.d,
        wealth: BUDGET * (1 + s.mean),
        risk: BUDGET * s.std,
        sharpe: s.sharpe,
        diff: BUDGET * (s.mean - b.mean),
        win: s.win,
        adj: BUDGET * (s.mean - (rfTotal + b.sharpe * s.std)),
      }));
      return { months: M, paths: done, rfWealth: BUDGET * (1 + rfTotal), baseSharpe: b.sharpe, rows };
    }

    return { step, result, total: p.paths, done: () => done };
  }

  // ------------------------------------------------------------ 2. 무한매수법 백테스트
  const DAY = 86400000;

  /** window.TQQQ ({start, gaps, p}) 를 날짜(ms, UTC) 배열과 가격 배열로 푼다. */
  function decodePrices(data) {
    const n = data.p.length;
    const t = new Float64Array(n);
    t[0] = Date.parse(data.start + "T00:00:00Z");
    for (let i = 1; i < n; i++) t[i] = t[i - 1] + (data.gaps.charCodeAt(i - 1) - 48) * DAY;
    return { t, p: Float64Array.from(data.p) };
  }

  function pathBuyHold(p) {
    return p.map((v) => v / p[0]);
  }

  /** path_dca: k번째 1/N 은 k일까지 무위험으로 불어난 뒤 k일 종가에 매수, 이후 보유. */
  function pathDca(p, N, rf) {
    const DT = 1 / 252;
    const out = new Float64Array(p.length);
    let sharesTot = 0;
    for (let t = 0; t < p.length; t++) {
      if (t < N) sharesTot += Math.exp(rf * DT * t) / p[t] / N;
      const unbought = Math.max(0, N - (t + 1)) / N;
      out[t] = sharesTot * p[t] + unbought * Math.exp(rf * DT * t);
    }
    return out;
  }

  /** path_infinite 의 이식. 매일 자산, 노출, 사이클 기록. */
  function pathInfinite(p, N, tp, rf) {
    const G = Math.exp(rf / 252);
    const days = p.length - 1;
    let cash = 1, shares = 0, cost = 0, bought = 0;
    let unit = cash / N;
    const wealth = new Float64Array(days + 1);
    const expo = new Float64Array(days);
    const cycles = [];
    const fullSpells = [];
    let start = 0, fullSince = null;
    for (let t = 0; t < days; t++) {
      const s = p[t];
      if (t) cash *= G;
      const sell = shares > 0 && s * shares >= (1 + tp) * cost;
      if (sell) {
        cash += shares * s;
        shares = cost = 0;
        bought = 0;
        unit = cash / N;
        cycles.push([start, t]);
        if (fullSince !== null) { fullSpells.push([fullSince, t]); fullSince = null; }
        start = t + 1;
      } else if (bought < N) {
        const amount = Math.min(unit, cash);
        shares += amount / s;
        cost += amount;
        cash -= amount;
        bought += 1;
        if (bought === N) fullSince = t;
      }
      wealth[t] = cash + shares * s;
      expo[t] = (shares * s) / wealth[t];
    }
    cash *= G;
    wealth[days] = cash + shares * p[days];
    const openCycle = shares > 0 ? [start, days] : null;
    if (fullSince !== null) fullSpells.push([fullSince, days]);
    let e = 0;
    for (let i = 0; i < days; i++) e += expo[i];
    return {
      wealth, exposure: e / days, expoLast: expo[days - 1], cycles, openCycle, fullSpells,
      openPnl: shares > 0 ? (shares * p[days]) / cost - 1 : null,
    };
  }

  function pathConstantMix(p, f, rf) {
    const g = Math.exp(rf / 252) - 1;
    const out = new Float64Array(p.length);
    out[0] = 1;
    for (let t = 1; t < p.length; t++) out[t] = out[t - 1] * (1 + f * (p[t] / p[t - 1] - 1) + (1 - f) * g);
    return out;
  }

  function pathMetrics(w, t, rf) {
    const years = (t[t.length - 1] - t[0]) / DAY / 365.25;
    const n = w.length - 1;
    let m = 0;
    for (let i = 1; i <= n; i++) m += w[i] / w[i - 1] - 1;
    m /= n;
    let v = 0;
    for (let i = 1; i <= n; i++) { const d = w[i] / w[i - 1] - 1 - m; v += d * d; }
    const vol = Math.sqrt(v / n) * Math.sqrt(252);
    const sharpe = vol > 0 ? ((m - (Math.exp(rf / 252) - 1)) * 252) / vol : NaN;
    let peak = -Infinity, mdd = 0, mddI = 0;
    for (let i = 0; i <= n; i++) {
      if (w[i] > peak) peak = w[i];
      const dd = w[i] / peak - 1;
      if (dd < mdd) { mdd = dd; mddI = i; }
    }
    return { final: BUDGET * w[n], cagr: Math.pow(w[n], 1 / years) - 1, vol, sharpe, mdd, mddT: t[mddI] };
  }

  /**
   * backtest_tqqq.full_period 의 이식.
   * d = decodePrices 결과, q = { splits, tp, rf, i0, i1 } (i0..i1 은 포함 인덱스)
   */
  function backtest(d, q) {
    const p = d.p.slice(q.i0, q.i1 + 1);
    const t = d.t.slice(q.i0, q.i1 + 1);
    const N = q.splits;
    const inf = pathInfinite(p, N, q.tp, q.rf);
    const f = inf.exposure;
    const curves = [
      { key: "bh", name: "기준군: 0시점 전액매수", w: pathBuyHold(p) },
      { key: "dca", name: `${N}일 분할매수 후 보유`, w: pathDca(p, N, q.rf) },
      { key: "inf", name: "무한매수법", w: inf.wealth },
      { key: "mix", name: `일정비중 ${(f * 100).toFixed(0)}% (동일노출)`, w: pathConstantMix(p, f, q.rf) },
    ];
    curves.forEach((c) => (c.m = pathMetrics(c.w, t, q.rf)));
    const days = p.length - 1;
    const years = (t[days] - t[0]) / DAY / 365.25;

    // 가장 오래 걸린 사이클: 완료 사이클 + 진행 중 사이클, 길이가 같으면 늦게 시작한 것 (Python max(tuple) 과 같게)
    const lens = inf.cycles.map(([a, b]) => ({ L: b - a + 1, a, b, open: false }));
    if (inf.openCycle) lens.push({ L: inf.openCycle[1] - inf.openCycle[0] + 1, a: inf.openCycle[0], b: days, open: true });
    let longest = null;
    for (const x of lens) if (!longest || x.L > longest.L || (x.L === longest.L && x.a > longest.a)) longest = x;
    const sorted = lens.map((x) => x.L).sort((a, b) => a - b);
    const median = sorted.length
      ? (sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2)
      : null;
    let wait = null;
    for (const [a, b] of inf.fullSpells) {
      const D = b - a;
      if (!wait || D > wait.D || (D === wait.D && a > wait.a)) wait = { D, a, b };
    }
    return {
      t, p, days, years, curves, exposure: f,
      rfFinal: BUDGET * Math.exp(q.rf * years),
      cycles: inf.cycles.length, medianLen: median,
      longest: longest && { L: longest.L, start: t[longest.a], end: longest.open ? null : t[longest.b] },
      wait: wait && { D: wait.D, start: t[wait.a], end: t[wait.b], count: inf.fullSpells.length },
      open: inf.openCycle && { start: t[inf.openCycle[0]], pnl: inf.openPnl, expoLast: inf.expoLast },
    };
  }

  const Calc = { makeRng, durationsFor, durationSim, decodePrices, pathBuyHold, pathDca, pathInfinite,
    pathConstantMix, pathMetrics, backtest, BUDGET };
  if (typeof module !== "undefined" && module.exports) module.exports = Calc;
  else root.Calc = Calc;
})(typeof self !== "undefined" ? self : this);
