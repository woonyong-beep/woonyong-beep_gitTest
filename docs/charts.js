/* SVG 차트 두 개: 위험–수익 평면, 로그 눈금 자산 추이. 외부 라이브러리 없이 직접 그린다. */
(function (root) {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";

  function el(name, attrs, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, str, attrs) {
    const t = el("text", Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = str;
    return t;
  }

  // ------------------------------------------------------------ 툴팁 (화면 고정 좌표)
  const tip = () => document.getElementById("tooltip");
  function showTip(html, cx, cy) {
    const t = tip();
    t.innerHTML = html;
    t.hidden = false;
    const w = t.offsetWidth, h = t.offsetHeight;
    const vw = document.documentElement.clientWidth, vh = window.innerHeight;
    let x = cx + 14, y = cy - h - 12;
    if (x + w > vw - 8) x = cx - w - 14;
    if (x < 8) x = Math.max(8, Math.min(vw - w - 8, cx - w / 2));
    if (y < 8) y = cy + 18;
    if (y + h > vh - 8) y = vh - h - 8;
    t.style.left = x + "px";
    t.style.top = y + "px";
  }
  function hideTip() { tip().hidden = true; }

  // ------------------------------------------------------------ 눈금
  function niceStep(span, target) {
    const raw = span / Math.max(1, target);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / mag;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  }
  function linTicks(lo, hi, target) {
    const s = niceStep(hi - lo, target);
    const out = [];
    for (let v = Math.ceil(lo / s - 1e-9) * s; v <= hi + 1e-9; v += s) out.push(+v.toFixed(10));
    return { ticks: out, step: s };
  }
  function logTicks(lo, hi) {
    for (const mult of [[1], [1, 2, 5], [1, 1.5, 2, 3, 5, 7], [1, 1.2, 1.4, 1.6, 1.8, 2, 2.5, 3, 4, 5, 6, 7, 8, 9]]) {
      const out = [];
      for (let k = Math.floor(Math.log10(lo)) - 1; k <= Math.ceil(Math.log10(hi)); k++)
        for (const m of mult) { const v = m * Math.pow(10, k); if (v >= lo && v <= hi) out.push(v); }
      if (out.length >= 4) return out;
    }
    return [lo, hi];
  }
  const fmtNum = (v) => v >= 1000 ? Math.round(v).toLocaleString("ko-KR") : (+v.toPrecision(3)).toLocaleString("ko-KR");

  function size(container, ratio, minH, maxH) {
    const w = Math.max(280, container.clientWidth - 16);
    const r = w < 520 ? Math.max(ratio, 0.85) : ratio;   // 좁은 화면에서는 세로를 더 준다
    return { w, h: Math.round(Math.max(minH, Math.min(maxH, w * r))) };
  }

  // ------------------------------------------------------------ 1. 위험–수익 평면
  function riskReturn(container, res) {
    container.innerHTML = "";
    const { w, h } = size(container, 0.56, 260, 440);
    const m = { l: 48, r: 16, t: 14, b: 40 };
    const rows = res.rows;
    const maxRisk = Math.max(...rows.map((r) => r.risk));
    const x1 = maxRisk * 1.12;
    const cml = (x) => res.rfWealth + res.baseSharpe * x;
    const ys = rows.map((r) => r.wealth).concat([res.rfWealth, cml(x1)]);
    let y0 = Math.min(...ys), y1 = Math.max(...ys);
    const pad = (y1 - y0) * 0.08 || 1;
    y0 -= pad; y1 += pad;
    const X = (v) => m.l + (v / x1) * (w - m.l - m.r);
    const Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (h - m.t - m.b);

    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": "위험과 기대만기자산 산점도" }, container);
    const g = el("g", {}, svg);
    for (const v of linTicks(y0, y1, Math.max(3, Math.round(h / 60))).ticks) {
      el("line", { x1: m.l, x2: w - m.r, y1: Y(v), y2: Y(v), class: "grid-line" }, g);
      text(g, m.l - 6, Y(v) + 4, fmtNum(v), { "text-anchor": "end" });
    }
    for (const v of linTicks(0, x1, Math.max(3, Math.round(w / 90))).ticks) {
      text(g, X(v), h - m.b + 16, fmtNum(v), { "text-anchor": "middle" });
    }
    el("line", { x1: m.l, x2: w - m.r, y1: h - m.b, y2: h - m.b, class: "axis-line" }, g);
    text(g, (m.l + w - m.r) / 2, h - 4, "위험 (만기 자산의 표준편차)", { "text-anchor": "middle", class: "axis-title" });
    text(g, m.l, m.t - 2, "기대만기자산", { class: "axis-title" });

    // CML
    el("line", { x1: X(0), y1: Y(cml(0)), x2: X(x1), y2: Y(cml(x1)), style: "stroke:var(--neutral);stroke-width:1.5", "stroke-dasharray": "5 4" }, g);
    // 듀레이션 연결선
    const pts = rows.map((r) => [X(r.risk), Y(r.wealth)]);
    el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", style: "stroke:var(--s2);stroke-width:2", "stroke-linejoin": "round" }, g);

    const placed = [];
    function placeLabel(x, y, str, bold) {
      const tw = str.length * 6.6 + 4, th = 13;
      const cands = [[x + 9, y + 4, "start"], [x - 9, y + 4, "end"], [x, y - 11, "middle"], [x, y + 19, "middle"]];
      for (const [lx, ly, anchor] of cands) {
        const bx = anchor === "start" ? lx : anchor === "end" ? lx - tw : lx - tw / 2;
        const box = [bx, ly - th + 3, bx + tw, ly + 3];
        if (box[0] < m.l || box[2] > w - 2 || box[1] < 0 || box[3] > h - m.b) continue;
        if (placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) continue;
        placed.push(box);
        const t = text(g, lx, ly, str, { "text-anchor": anchor });
        if (bold) t.setAttribute("style", "font-weight:600;fill:var(--text)");
        return;
      }
    }
    // 무위험점
    const rfPt = [X(0), Y(res.rfWealth)];
    el("circle", { cx: rfPt[0], cy: rfPt[1], r: 4.5, style: "fill:var(--neutral);stroke:var(--surface);stroke-width:2" }, g);
    placed.push([rfPt[0] - 5, rfPt[1] - 5, rfPt[0] + 5, rfPt[1] + 5]);
    pts.forEach((p) => placed.push([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5]));
    placeLabel(rfPt[0], rfPt[1], "무위험", false);

    rows.forEach((r, i) => {
      const [x, y] = pts[i];
      el("circle", { cx: x, cy: y, r: i === 0 ? 6 : 4.5, style: `fill:var(${i === 0 ? "--s1" : "--s2"});stroke:var(--surface);stroke-width:2` }, g);
    });
    rows.forEach((r, i) => placeLabel(pts[i][0], pts[i][1], i === 0 ? "기준군" : `D=${r.d}`, i === 0));

    // 히트 영역
    const hits = rows.map((r, i) => ({ x: pts[i][0], y: pts[i][1], html:
      `<div class="t">${r.name}</div><div class="r"><span>기대만기자산</span><b>${r.wealth.toFixed(1)}</b></div>` +
      `<div class="r"><span>위험</span><b>${r.risk.toFixed(1)}</b></div><div class="r"><span>샤프</span><b>${r.sharpe.toFixed(3)}</b></div>` +
      (i ? `<div class="r"><span>위험조정 초과</span><b>${signed(r.adj, 1)}</b></div>` : "") }));
    hits.push({ x: rfPt[0], y: rfPt[1], html: `<div class="t">전액 무위험채권</div><div class="r"><span>만기자산</span><b>${res.rfWealth.toFixed(1)}</b></div>` });
    const ring = el("circle", { r: 9, fill: "none", style: "stroke:var(--text);stroke-width:1.5", visibility: "hidden" }, g);
    const overlay = el("rect", { x: 0, y: 0, width: w, height: h, fill: "transparent" }, svg);
    function move(ev) {
      const b = svg.getBoundingClientRect();
      const sx = ((ev.clientX - b.left) * w) / b.width, sy = ((ev.clientY - b.top) * h) / b.height;
      let best = null, bd = 22 * 22;
      for (const p of hits) { const d = (p.x - sx) ** 2 + (p.y - sy) ** 2; if (d < bd) { bd = d; best = p; } }
      if (!best) { ring.setAttribute("visibility", "hidden"); hideTip(); return; }
      ring.setAttribute("cx", best.x); ring.setAttribute("cy", best.y); ring.setAttribute("visibility", "visible");
      showTip(best.html, ev.clientX, ev.clientY);
    }
    overlay.addEventListener("pointermove", move);
    overlay.addEventListener("pointerdown", move);
    overlay.addEventListener("pointerleave", (ev) => { if (ev.pointerType === "touch") return; ring.setAttribute("visibility", "hidden"); hideTip(); });

    legend(container, [
      { color: "--s1", label: "기준군 (0시점 전액매수)", dot: true },
      { color: "--s2", label: "분할매수 듀레이션 D (개월)" },
      { color: "--neutral", label: "자본시장선 (기준군 + 무위험채권)", dash: true },
    ]);
  }

  function signed(v, d) { const s = v.toFixed(d); return (v >= 0 && !s.startsWith("-") ? "+" : "") + s.replace("-", "−"); }

  function legend(container, items) {
    const lg = document.createElement("div");
    lg.className = "legend";
    for (const it of items) {
      const s = document.createElement("span");
      const i = document.createElement("i");
      if (it.dot) { i.className = "dot"; i.style.background = `var(${it.color})`; }
      else { i.className = it.dash ? "dash" : ""; i.style.borderTopColor = `var(${it.color})`; }
      s.appendChild(i);
      s.appendChild(document.createTextNode(it.label));
      lg.appendChild(s);
    }
    container.insertBefore(lg, container.firstChild);
  }

  // ------------------------------------------------------------ 2. 자산 추이 (로그)
  const DAY = 86400000;
  const ymd = (ms) => new Date(ms).toISOString().slice(0, 10);

  function wealthChart(container, data) {
    // data = { t: Float64Array(ms), series: [{name, color, w: 배열(시작 1), dash?}] }  값은 100 배로 그린다
    container.innerHTML = "";
    const { w, h } = size(container, 0.55, 280, 460);
    const m = { l: 56, r: 14, t: 12, b: 30 };
    const t = data.t, n = t.length;
    let lo = Infinity, hi = -Infinity;
    for (const s of data.series) for (let i = 0; i < n; i++) { const v = 100 * s.w[i]; if (v < lo) lo = v; if (v > hi) hi = v; }
    const lpad = (Math.log(hi) - Math.log(lo)) * 0.04 || 0.05;
    const L0 = Math.log(lo) - lpad, L1 = Math.log(hi) + lpad;
    const X = (ms) => m.l + ((ms - t[0]) / (t[n - 1] - t[0] || 1)) * (w - m.l - m.r);
    const Y = (v) => m.t + (1 - (Math.log(v) - L0) / (L1 - L0)) * (h - m.t - m.b);

    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": "전략별 자산 추이, 로그 눈금" }, container);
    const g = el("g", {}, svg);
    for (const v of logTicks(Math.exp(L0), Math.exp(L1))) {
      el("line", { x1: m.l, x2: w - m.r, y1: Y(v), y2: Y(v), class: "grid-line" }, g);
      text(g, m.l - 6, Y(v) + 4, fmtNum(v), { "text-anchor": "end" });
    }
    // 가로축: 연 단위 또는 월 단위
    const spanY = (t[n - 1] - t[0]) / DAY / 365.25;
    const maxLabels = Math.max(2, Math.floor((w - m.l - m.r) / 64));
    const d0 = new Date(t[0]), d1 = new Date(t[n - 1]);
    const xt = [];
    if (spanY >= 2) {
      const step = Math.max(1, Math.ceil(spanY / maxLabels));
      for (let y = d0.getUTCFullYear() + 1; y <= d1.getUTCFullYear(); y++)
        if (y % step === 0) xt.push([Date.UTC(y, 0, 1), String(y)]);
    } else {
      const months = (d1.getUTCFullYear() - d0.getUTCFullYear()) * 12 + d1.getUTCMonth() - d0.getUTCMonth();
      const step = [1, 2, 3, 6, 12].find((s) => months / s <= maxLabels) || 12;
      for (let k = 1; k <= months; k++) {
        const ms = Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + k, 1);
        const dd = new Date(ms);
        if (dd.getUTCMonth() % step === 0) xt.push([ms, `${dd.getUTCFullYear()}.${String(dd.getUTCMonth() + 1).padStart(2, "0")}`]);
      }
    }
    for (const [ms, lab] of xt) {
      el("line", { x1: X(ms), x2: X(ms), y1: h - m.b, y2: h - m.b + 4, class: "axis-line" }, g);
      text(g, X(ms), h - m.b + 17, lab, { "text-anchor": "middle" });
    }
    el("line", { x1: m.l, x2: w - m.r, y1: h - m.b, y2: h - m.b, class: "axis-line" }, g);

    // 선: 화면 폭에 비해 점이 많으면 픽셀 칸마다 최소/최대만 남긴다 (모양 보존)
    const pxPer = (w - m.l - m.r) / n;
    for (const s of data.series) {
      let d = "";
      if (pxPer >= 0.5) {
        for (let i = 0; i < n; i++) d += (i ? "L" : "M") + X(t[i]).toFixed(1) + "," + Y(100 * s.w[i]).toFixed(1);
      } else {
        const bucket = Math.ceil(0.5 / pxPer);
        for (let i = 0; i < n; i += bucket) {
          let a = i, b = i;
          for (let j = i; j < Math.min(n, i + bucket); j++) { if (s.w[j] < s.w[a]) a = j; if (s.w[j] > s.w[b]) b = j; }
          for (const k of a < b ? [a, b] : [b, a]) d += (d ? "L" : "M") + X(t[k]).toFixed(1) + "," + Y(100 * s.w[k]).toFixed(1);
        }
        d += "L" + X(t[n - 1]).toFixed(1) + "," + Y(100 * s.w[n - 1]).toFixed(1);
      }
      el("path", { d, fill: "none", style: `stroke:var(${s.color});stroke-width:${s.dash ? 1.5 : 2}`, "stroke-linejoin": "round",
        "stroke-dasharray": s.dash ? "5 4" : "none" }, g);
    }

    // 크로스헤어
    const vline = el("line", { y1: m.t, y2: h - m.b, class: "axis-line", visibility: "hidden" }, g);
    const dots = data.series.map((s) => el("circle", { r: 4, style: `fill:var(${s.color});stroke:var(--surface);stroke-width:2`, visibility: "hidden" }, g));
    const overlay = el("rect", { x: m.l, y: 0, width: w - m.l - m.r, height: h, fill: "transparent" }, svg);
    function move(ev) {
      const b = svg.getBoundingClientRect();
      const sx = ((ev.clientX - b.left) * w) / b.width;
      const ms = t[0] + ((sx - m.l) / (w - m.l - m.r)) * (t[n - 1] - t[0]);
      let a = 0, z = n - 1;
      while (z - a > 1) { const mid = (a + z) >> 1; if (t[mid] <= ms) a = mid; else z = mid; }
      const i = Math.abs(t[a] - ms) <= Math.abs(t[z] - ms) ? a : z;
      const x = X(t[i]);
      vline.setAttribute("x1", x); vline.setAttribute("x2", x); vline.setAttribute("visibility", "visible");
      let html = `<div class="t">${ymd(t[i])}</div>`;
      data.series.forEach((s, k) => {
        dots[k].setAttribute("cx", x); dots[k].setAttribute("cy", Y(100 * s.w[i])); dots[k].setAttribute("visibility", "visible");
        html += `<div class="r"><span><i class="sw" style="background:var(${s.color})"></i>${s.short || s.name}</span><b>${fmtNum(100 * s.w[i])}</b></div>`;
      });
      showTip(html, ev.clientX, ev.clientY);
    }
    function leave(ev) { if (ev && ev.pointerType === "touch") return; vline.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); }
    overlay.addEventListener("pointermove", move);
    overlay.addEventListener("pointerdown", move);
    overlay.addEventListener("pointerleave", leave);

    legend(container, data.series.map((s) => ({ color: s.color, dash: s.dash, label: `${s.name}: ${fmtNum(100 * s.w[n - 1])}` })));
  }

  // 터치 화면: 차트 밖을 누르면 툴팁을 닫는다 (터치는 pointerleave 로 닫지 않으므로)
  document.addEventListener("pointerdown", (ev) => { if (!ev.target.closest || !ev.target.closest(".chart")) hideTip(); });

  root.Charts = { riskReturn, wealthChart, showTip, hideTip, signed };
})(window);
