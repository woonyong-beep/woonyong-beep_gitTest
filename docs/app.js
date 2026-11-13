/* 화면 연결: 탭, 입력, 실행, 표와 차트 그리기. 계산은 calc.js, 그림은 charts.js. */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const pct = (v, d = 1) => (v * 100).toFixed(d).replace("-", "−") + "%";
  const num = (v, d = 1) => v.toFixed(d).replace("-", "−");
  const signed = Charts.signed;
  const DAY = 86400000;
  const ymd = (ms) => new Date(ms).toISOString().slice(0, 10);
  const last = { duration: null, infinite: null };

  // ------------------------------------------------------------ 탭
  const tabs = [$("#tab-duration"), $("#tab-infinite"), $("#tab-dart")];
  const HASH = ["#duration", "#infinite", "#dart"];
  function selectTab(btn, focus) {
    for (const b of tabs) {
      const on = b === btn;
      b.setAttribute("aria-selected", on);
      b.tabIndex = on ? 0 : -1;
      document.getElementById(b.getAttribute("aria-controls")).hidden = !on;
    }
    if (focus) btn.focus();
    history.replaceState(null, "", HASH[tabs.indexOf(btn)]);
    Charts.hideTip();
    redraw();
  }
  tabs.forEach((b, i) => {
    b.addEventListener("click", () => selectTab(b));
    b.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        selectTab(tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length], true);
      }
    });
  });

  function readNum(form, name) {
    const inp = form.elements[name];
    const v = parseFloat(inp.value);
    const min = parseFloat(inp.min), max = parseFloat(inp.max);
    const label = inp.closest(".field").querySelector("span").textContent;
    if (!Number.isFinite(v)) throw new Error(`${label}: 숫자를 입력하세요.`);
    if (v < min || v > max) throw new Error(`${label}: ${min} 이상 ${max} 이하로 입력하세요.`);
    return v;
  }

  // ------------------------------------------------------------ 1. 매수듀레이션
  const fd = $("#form-duration");
  const PRESETS = {
    rw: { mu: 8, sigma: 16, rf: 3, years: 5, model: "rw", kappa: 0.5, x0: 0 },
    mr: { mu: 8, sigma: 16, rf: 3, years: 5, model: "mr", kappa: 0.5, x0: 0 },
    mr20: { mu: 8, sigma: 16, rf: 3, years: 5, model: "mr", kappa: 0.5, x0: 20 },
  };
  function syncModel() {
    const mr = fd.elements.model.value === "mr";
    fd.querySelectorAll(".mr-only").forEach((e) => e.classList.toggle("is-hidden", !mr));
  }
  fd.elements.model.addEventListener("change", syncModel);
  fd.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    const p = PRESETS[b.dataset.preset];
    for (const k in p) fd.elements[k].value = p[k];
    syncModel();
    runDuration();
  }));

  let runToken = 0;
  function runDuration() {
    const err = $("#error-duration");
    err.textContent = "";
    let p;
    try {
      const mr = fd.elements.model.value === "mr";
      p = {
        mu: readNum(fd, "mu") / 100, sigma: readNum(fd, "sigma") / 100, rf: readNum(fd, "rf") / 100,
        years: readNum(fd, "years"),
        kappa: mr ? readNum(fd, "kappa") : 0, x0: mr ? readNum(fd, "x0") / 100 : 0,
        paths: parseInt(fd.elements.paths.value, 10), seed: Math.round(readNum(fd, "seed")), model: mr ? "mr" : "rw",
      };
    } catch (e) { err.textContent = e.message; return; }

    const token = ++runToken;
    const sim = Calc.durationSim(p);
    const btn = $("#run-duration"), prog = $("#progress-duration");
    btn.disabled = true;
    prog.hidden = false;
    const t0 = performance.now();
    const CHUNK = 5000;
    function tick() {
      if (token !== runToken) return;          // 더 새 실행이 시작됨
      const sliceEnd = performance.now() + 40;
      let done;
      do { done = sim.step(CHUNK); } while (done < sim.total && performance.now() < sliceEnd);
      prog.querySelector("i").style.width = (100 * done) / sim.total + "%";
      prog.querySelector("span").textContent = `${done.toLocaleString("ko-KR")} / ${sim.total.toLocaleString("ko-KR")} 경로`;
      if (done < sim.total) { setTimeout(tick, 0); return; }
      btn.disabled = false;
      prog.hidden = true;
      last.duration = { p, res: sim.result(), ms: performance.now() - t0 };
      renderDuration();
    }
    setTimeout(tick, 0);
  }
  fd.addEventListener("submit", (e) => { e.preventDefault(); runDuration(); });

  function renderDuration() {
    const { p, res, ms } = last.duration;
    const model = p.model === "rw" ? "랜덤워크" : `평균회귀 (κ ${p.kappa}, 시작 괴리 ${signed(p.x0 * 100, 0)}%)`;
    $("#summary-duration").textContent =
      `${model}, 기대수익률 ${num(p.mu * 100, 1)}%, 변동성 ${num(p.sigma * 100, 1)}%, 무위험 ${num(p.rf * 100, 2)}%, ` +
      `${res.months}개월, 경로 ${res.paths.toLocaleString("ko-KR")}개 (시드 ${p.seed}, ${(ms / 1000).toFixed(2)}초). ` +
      `예산 100을 전액 무위험채권에 두면 만기 자산 ${res.rfWealth.toFixed(1)}.`;
    const head = ["전략", "기대만기자산", "위험", "샤프", "기준군 대비", "기준군 이길 확률", "위험조정 초과"];
    let html = "<thead><tr>" + head.map((h) => `<th scope="col">${h}</th>`).join("") + "</tr></thead><tbody>";
    res.rows.forEach((r, i) => {
      const sw = `<span class="swatch" style="background:var(${i ? "--s2" : "--s1"})"></span>`;
      html += `<tr class="${i ? "" : "base"}"><td>${sw}${r.name}</td><td>${r.wealth.toFixed(1)}</td><td>${r.risk.toFixed(1)}</td>` +
        `<td>${r.sharpe.toFixed(3)}</td>` +
        (i ? `<td>${signed(r.diff, 1)}</td><td>${pct(r.win)}</td><td>${signed(r.adj, 1)}</td>`
           : `<td>기준</td><td>–</td><td>–</td>`) + "</tr>";
    });
    $("#table-duration").innerHTML = html + "</tbody>";
    Charts.riskReturn($("#chart-duration"), res);
  }

  // ------------------------------------------------------------ 2. 무한매수법
  const data = Calc.decodePrices(window.TQQQ);
  const fi = $("#form-infinite");
  const first = ymd(data.t[0]), lastDay = ymd(data.t[data.t.length - 1]);
  $("#data-range").textContent = `수록 기간 ${first} ~ ${lastDay}, ${data.p.length.toLocaleString("ko-KR")}거래일.`;
  for (const k of ["start", "end"]) { fi.elements[k].min = first; fi.elements[k].max = lastDay; }
  function resetInfinite() {
    fi.elements.splits.value = 40; fi.elements.tp.value = 10; fi.elements.rf.value = 3;
    fi.elements.start.value = first; fi.elements.end.value = lastDay;
  }
  resetInfinite();
  $("#reset-infinite").addEventListener("click", () => { resetInfinite(); runInfinite(); });

  function runInfinite() {
    const err = $("#error-infinite");
    err.textContent = "";
    let q;
    try {
      const splits = Math.round(readNum(fi, "splits"));
      const tp = readNum(fi, "tp") / 100, rf = readNum(fi, "rf") / 100;
      const s = Date.parse(fi.elements.start.value + "T00:00:00Z"), e = Date.parse(fi.elements.end.value + "T00:00:00Z");
      if (!Number.isFinite(s) || !Number.isFinite(e)) throw new Error("시작일과 종료일을 입력하세요.");
      let i0 = data.t.findIndex((v) => v >= s);
      let i1 = -1;
      for (let i = data.t.length - 1; i >= 0; i--) if (data.t[i] <= e) { i1 = i; break; }
      if (i0 < 0 || i1 < 0 || i1 <= i0) throw new Error("시작일이 종료일보다 앞서야 하고, 그 사이에 거래일이 있어야 합니다.");
      if (i1 - i0 + 1 < splits + 1) throw new Error(`기간이 너무 짧습니다. 분할 횟수(${splits})보다 거래일이 많아야 합니다 (현재 ${i1 - i0 + 1}거래일).`);
      q = { splits, tp, rf, i0, i1 };
    } catch (ex) { err.textContent = ex.message; return; }
    last.infinite = { q, r: Calc.backtest(data, q) };
    renderInfinite();
  }
  fi.addEventListener("submit", (e) => { e.preventDefault(); runInfinite(); });
  fi.addEventListener("change", runInfinite);

  const COLORS = ["--s1", "--s2", "--s3", "--s4"];
  function renderInfinite() {
    const { q, r } = last.infinite;
    $("#summary-infinite").textContent =
      `${ymd(r.t[0])} ~ ${ymd(r.t[r.days])} (${r.years.toFixed(1)}년, ${r.days.toLocaleString("ko-KR")}거래일), 시작 자산 100. ` +
      `분할 ${q.splits}회, 익절 +${+(q.tp * 100).toFixed(2)}%, 무위험수익률 연 ${+(q.rf * 100).toFixed(2)}% 고정 가정. ` +
      `전액 무위험이면 만기 자산 ${r.rfFinal.toFixed(1)}.`;
    const head = ["전략", "만기자산", "연복리수익률", "변동성", "샤프", "최대낙폭"];
    let html = "<thead><tr>" + head.map((h) => `<th scope="col">${h}</th>`).join("") + "</tr></thead><tbody>";
    r.curves.forEach((c, i) => {
      const m = c.m;
      html += `<tr class="${c.key === "inf" ? "hl" : ""}"><td><span class="swatch" style="background:var(${COLORS[i]})"></span>${c.name}</td>` +
        `<td>${Math.round(m.final).toLocaleString("ko-KR")}</td><td>${pct(m.cagr)}</td><td>${pct(m.vol)}</td>` +
        `<td>${Number.isFinite(m.sharpe) ? m.sharpe.toFixed(2) : "–"}</td><td>${pct(m.mdd)}<span class="sub">${ymd(m.mddT)}</span></td></tr>`;
    });
    $("#table-infinite").innerHTML = html + "</tbody>";

    const L = r.longest;
    $("#tiles-infinite").innerHTML =
      tile("완료 사이클 수", `${r.cycles}회`, r.medianLen !== null ? `사이클 길이 중앙값 ${r.medianLen}거래일` : "") +
      tile("평균 주식 비중", pct(r.exposure), "전 기간 매일 비중의 평균") +
      tile("가장 오래 걸린 사이클", L ? `${L.L.toLocaleString("ko-KR")}거래일` : "–",
        L ? `${ymd(L.start)} ~ ${L.end === null ? "종료일 현재 미완료" : ymd(L.end)}` : "");
    const facts = [];
    if (r.wait) facts.push(`${q.splits}회분을 모두 쓴 뒤 익절까지 가장 오래 기다린 기간: ${r.wait.D.toLocaleString("ko-KR")}거래일 (${ymd(r.wait.start)} ~ ${ymd(r.wait.end)}). ${q.splits}회분 소진은 총 ${r.wait.count}번.`);
    else facts.push(`${q.splits}회분을 모두 쓴 적이 없습니다.`);
    if (r.open) facts.push(`종료일 상태: ${ymd(r.open.start)}에 시작한 사이클 진행 중, 평단 대비 평가손익 ${signed(r.open.pnl * 100, 1)}%, 종료일 주식 비중 ${pct(r.open.expoLast, 0)}.`);
    else facts.push("종료일 상태: 진행 중인 사이클 없음 (전액 현금).");
    $("#facts-infinite").innerHTML = facts.map((f) => `<li>${f}</li>`).join("");

    const rf = Float64Array.from(r.t, (ms) => Math.exp(q.rf * ((ms - r.t[0]) / DAY / 365.25)));
    const shorts = ["기준군", "분할매수", "무한매수법", "일정비중"];
    Charts.wealthChart($("#chart-infinite"), {
      t: r.t,
      series: r.curves.map((c, i) => ({ name: c.name, short: shorts[i], color: COLORS[i], w: c.w }))
        .concat([{ name: `무위험 연 ${+(q.rf * 100).toFixed(2)}% (가정)`, short: "무위험", color: "--neutral", w: rf, dash: true }]),
    });
  }
  function tile(k, v, s) { return `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`; }

  // ------------------------------------------------------------ 다시 그리기 (창 크기, 탭 전환)
  function redraw() {
    if (!$("#panel-duration").hidden && last.duration) Charts.riskReturn($("#chart-duration"), last.duration.res);
    if (!$("#panel-infinite").hidden && last.infinite) renderInfinite();
    if (!$("#panel-dart").hidden && window.DartView) window.DartView.show();
  }
  let rt, lastW = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastW) return;   // 모바일 주소창 높이 변화는 무시
    lastW = window.innerWidth;
    clearTimeout(rt); rt = setTimeout(redraw, 150);
  });

  // ------------------------------------------------------------ 시작
  syncModel();
  if (HASH.indexOf(location.hash) > 0) selectTab(tabs[HASH.indexOf(location.hash)]);
  runInfinite();
  runDuration();
})();
