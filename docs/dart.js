/* 3번 탭 "재무제표 탐색": DART 표준화 재무제표 보기, 출처 패널, 회사 간 비교, 검증 상태.
   데이터는 dart-data.js (tools/make_web_dart.py 가 만든다). 탭을 처음 열 때 불러온다. */
(function (root) {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const NS = "http://www.w3.org/2000/svg";

  // ------------------------------------------------------------ 표시용 이름
  const STMT = { BS: "재무상태표", PL: "손익" };
  const SJ = { BS: "재무상태표 (BS)", IS: "손익계산서 (IS)", CIS: "포괄손익계산서 (CIS)" };
  const FS = { CFS: "연결", OFS: "별도" };
  const METHOD = { xbrl_id: "XBRL 계정 id 로 연결", name: "계정명으로 연결", position: "표 안의 위치로 연결 (산술 대사로 확인)", manual: "수작업 판단" };
  const CONF = { high: "높음", medium: "중간", low: "낮음" };
  const REVIEW = { ok: "검토 완료", needs_lead: "연구 책임 확인 필요" };
  const KIND = { total: "총계", subtotal: "소계", group: "묶음", item: "항목", formula: "공식 항목", attribution: "귀속", per_share: "주당 금액" };
  const STATUS = { pass: "통과", fail: "실패", missing: "값 없음", one_side: "한쪽만 있음" };
  const UNITS = {
    jo: { div: 1e12, d: 2, label: "조 원" },
    eok: { div: 1e8, d: 0, label: "억 원" },
    mil: { div: 1e6, d: 0, label: "백만 원" },
    won: { div: 1, d: 0, label: "원" },
  };
  const SHORT = { "현대자동차": "현대차", "LG에너지솔루션": "LG엔솔", "SK하이닉스": "SK하이닉스" };

  let D = null;              // window.DART
  let M = null;              // 모델
  const state = {
    view: "company", corp: null, fs: "CFS", stmt: "BS", unit: "jo", showEmpty: false,
    open: { BS: null, PL: null },       // 펼친 노드 집합 (null 이면 기본값)
    cmp: "PL.OP", cmpFs: "CFS",
  };

  // ------------------------------------------------------------ 숫자
  function fmtWon(v) { return Math.round(v).toLocaleString("ko-KR").replace("-", "−"); }
  function fmt(v, unit, perShare) {
    if (v === null || v === undefined) return null;
    if (perShare) return fmtWon(v);
    const u = UNITS[unit];
    if (u.div === 1) return fmtWon(v);
    const x = v / u.div;
    let s = x.toLocaleString("ko-KR", { minimumFractionDigits: u.d, maximumFractionDigits: u.d });
    if (v !== 0 && Number(x.toFixed(u.d)) === 0) s = "≈" + (v < 0 ? "−" : "") + s.replace("-", "");
    return s.replace("-", "−");
  }
  const unitLabel = (unit, perShare) => perShare ? "원/주" : UNITS[unit].label;
  const ymd = (s) => s && s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}` : s;

  // ------------------------------------------------------------ 모델
  function buildModel(d) {
    const charts = {};
    for (const name of ["BS", "PL"]) {
      const nodes = new Map(), order = [];
      for (const [id, parent, sign, name_ko, name_en, kind, formula, note] of d.charts[name]) {
        nodes.set(id, { id, parent, sign, name: name_ko, en: name_en, kind, formula, note, children: [], stmt: name });
        order.push(id);
      }
      for (const n of nodes.values()) if (n.parent) nodes.get(n.parent).children.push(n.id);
      for (const n of nodes.values()) {
        let k = 0, p = n.parent;
        while (p) { k++; p = nodes.get(p).parent; }
        n.depth = k;
        n.terms = n.kind === "formula" ? (n.formula.replace(/\s/g, "").match(/[+-]?[^+-]+/g) || [])
          .map((t) => t[0] === "-" ? [t.slice(1), -1] : [t.replace(/^\+/, ""), 1]) : null;
      }
      charts[name] = { nodes, order, roots: order.filter((id) => !nodes.get(id).parent) };
    }
    const corpName = new Map(d.companies.map((c) => [c[0], c[1]]));
    const stOf = (corp, fs, year) => d.st[`${corp}|${fs}|${year}`] || null;

    /** 노드 값 {rep, roll, value, source} 또는 null (값 없음). */
    function val(corp, fs, year, stmt, sid) {
      const s = stOf(corp, fs, year);
      const v = s && s[stmt][sid];
      if (!v) return null;
      const node = charts[stmt].nodes.get(sid);
      const source = v[0] !== null ? "reported" : node.kind === "formula" ? "formula" : "rollup";
      return { rep: v[0], roll: v[1], value: v[0] !== null ? v[0] : v[1], source };
    }
    function stmtOf(sid) { return sid.startsWith("BS.") ? "BS" : "PL"; }

    /** 출처: 보고 줄, 점검용 줄, 하위(또는 공식) 구성, 실제로 더한 원본 줄(유효 부호 포함), 점검, 공시. */
    function provenance(corp, fs, year, stmt, sid) {
      const s = stOf(corp, fs, year);
      const ch = charts[stmt];
      const node = ch.nodes.get(sid);
      const v = val(corp, fs, year, stmt, sid);
      const maps = d.maps[stmt];
      const lineObj = (l) => {
        const m = maps[l[6]];
        return { raw_index: l[0], sj: l[1], account_id: l[2], account_nm: l[3], amount: l[4],
          std_id: m[0], role: m[1], flip: m[2], method: m[3], confidence: m[4], review: m[5], note: m[6],
          map_year: m[7], occurrence: m[8] };
      };
      const lines = s ? s.lines.filter((l) => l[5] === stmt).map(lineObj) : [];
      const own = lines.filter((l) => l.std_id === sid);
      const reported = own.filter((l) => l.role === "value");
      const checkOnly = own.filter((l) => l.role === "check_only");
      // 하위 구성 (공식이면 피연산자)
      let parts = null;
      if (node.kind === "formula") parts = node.terms.map(([t, sg]) => ({ sid: t, sign: sg, v: val(corp, fs, year, stmt, t) }));
      else if (node.children.length) parts = node.children.map((k) => ({ sid: k, sign: ch.nodes.get(k).sign, v: val(corp, fs, year, stmt, k) }));
      // 합계·공식 값을 이루는 원본 줄 (유효 부호 = 경로의 부호 곱 × flip)
      function leaves(id, sign) {
        const x = val(corp, fs, year, stmt, id);
        if (!x) return [];
        if (x.rep !== null) return lines.filter((l) => l.std_id === id && l.role === "value").map((l) => ({ line: l, via: id, sign }));
        const n = ch.nodes.get(id);
        if (n.kind === "formula") return n.terms.flatMap(([t, sg]) => leaves(t, sign * sg));
        return n.children.flatMap((k) => leaves(k, sign * ch.nodes.get(k).sign));
      }
      let rollLeaves = [];
      if (v && v.roll !== null) {
        rollLeaves = node.kind === "formula" ? node.terms.flatMap(([t, sg]) => leaves(t, sg))
          : node.children.flatMap((k) => leaves(k, ch.nodes.get(k).sign));
      }
      // 값이 없을 때: 값이 있는 가장 가까운 상위 노드
      let ancestor = null;
      if (!v) {
        let p = node.parent;
        while (p) { const pv = val(corp, fs, year, stmt, p); if (pv) { ancestor = { sid: p, v: pv }; break; } p = ch.nodes.get(p).parent; }
      }
      const checks = s ? s.checks.filter((c) => c[0] === stmt && c[2] === sid)
        .map((c) => ({ check: c[1], status: c[3], reported: c[4], computed: c[5], diff: c[6] })) : [];
      return { corp, company: corpName.get(corp), fs, year, stmt, node, v, reported, checkOnly, parts, rollLeaves, ancestor, checks,
        filing: s ? { rcept_no: s.rcept_no, rcept_dt: s.rcept_dt, report_nm: s.report_nm, raw_file: s.raw_file } : null };
    }
    return { charts, val, provenance, stmtOf, corpName, stOf, companies: d.companies, years: d.years };
  }

  // ------------------------------------------------------------ 표의 행 순서
  // 재무상태표: 위에서 아래로 (부모 먼저). 손익: 소계·총계는 구성 항목 뒤에 (매출 → … → 당기순이익), 묶음은 앞에.
  function sections(stmt) {
    const ch = M.charts[stmt];
    const out = [];
    function walk(id, depth, rows, post) {
      const n = ch.nodes.get(id);
      const after = post && (n.kind === "total" || n.kind === "subtotal");
      if (!after) rows.push({ sid: id, depth });
      for (const k of n.children) {
        walk(k, depth + 1, rows, post);
        if (k === "PL.OPEX") rows.push({ sid: "PL.GP", depth: depth + 1, under: id });   // 매출총이익은 영업비용 묶음 바로 뒤
      }
      if (after) rows.push({ sid: id, depth });
    }
    if (stmt === "BS") {
      for (const r of ch.roots) { const rows = []; walk(r, 0, rows, false); out.push({ title: null, rows }); }
      return [{ title: null, rows: out.flatMap((s) => s.rows) }];
    }
    const sec = (title, ids, post) => { const rows = []; for (const id of ids) walk(id, 0, rows, post); out.push({ title, rows }); };
    sec("당기손익", ["PL.NI"], true);
    sec("당기순이익의 귀속", ["PL.NIO", "PL.NIN"], false);
    sec("기타포괄손익", ["PL.OCI"], true);
    sec("총포괄손익", ["PL.CI", "PL.CIO", "PL.CIN"], false);
    sec("주당이익 (원/주)", ch.order.filter((id) => ch.nodes.get(id).kind === "per_share"), false);
    return out;
  }
  function defaultOpen(stmt) {
    const ch = M.charts[stmt], s = new Set();
    for (const [id, n] of ch.nodes) {
      if (!n.children.length) continue;
      if (stmt === "BS" ? n.depth < 2 : !["PL.FININC", "PL.OCI.N", "PL.OCI.R", "PL.NIO", "PL.NIN"].includes(id)) s.add(id);
    }
    return s;
  }

  // ------------------------------------------------------------ 1. 회사별 보기
  function renderCompany() {
    const { corp, fs, stmt, unit } = state;
    if (!state.open[stmt]) state.open[stmt] = defaultOpen(stmt);
    const open = state.open[stmt];
    const ch = M.charts[stmt];
    const years = M.years;
    const has = (sid) => years.some((y) => M.val(corp, fs, y, stmt, sid));
    const visibleId = (sid) => state.showEmpty || has(sid);
    let html = `<caption class="sr-only">${esc(M.corpName.get(corp))} ${FS[fs]} ${STMT[stmt]}, 사업연도별 당기 금액 (${UNITS[unit].label})</caption>`;
    html += `<thead><tr><th scope="col">계정 <span class="unit-note">${esc(UNITS[unit].label)}</span></th>` +
      years.map((y) => `<th scope="col">${y}</th>`).join("") + "</tr></thead>";
    for (const sec of sections(stmt)) {
      const rows = sec.rows.filter((r) => visibleId(r.sid));
      if (!rows.length) continue;
      html += "<tbody>";
      if (sec.title) html += `<tr class="sec"><th scope="rowgroup" colspan="${years.length + 1}">${esc(sec.title)}</th></tr>`;
      // 접힌 조상이 있으면 숨긴다 (구획 안의 조상만)
      const inSec = new Set(sec.rows.map((r) => r.sid));
      for (const r of rows) {
        const n = ch.nodes.get(r.sid);
        let p = r.under || n.parent, hidden = false;     // under: 나무 밖 공식 행을 끼워 넣은 자리
        while (p && inSec.has(p)) { if (!open.has(p)) { hidden = true; break; } p = ch.nodes.get(p).parent; }
        if (hidden) continue;
        const kids = n.children.filter(visibleId);
        const perShare = n.kind === "per_share";
        const cls = ["k-" + (n.kind || "item")];
        const tog = kids.length
          ? `<button type="button" class="tog" data-sid="${n.id}" aria-expanded="${open.has(n.id)}" aria-label="${esc(n.name)} ${open.has(n.id) ? "접기" : "펼치기"}"><span aria-hidden="true">${open.has(n.id) ? "▾" : "▸"}</span></button>`
          : `<span class="tog-sp" aria-hidden="true"></span>`;
        html += `<tr class="${cls.join(" ")}" data-sid="${n.id}"><th scope="row" style="--d:${r.depth}"><span class="nm">${tog}<span class="lab" title="${esc(n.id)}">${esc(n.name)}${perShare ? ' <span class="u">원/주</span>' : ""}${n.kind === "formula" ? ' <span class="u">공식</span>' : ""}</span></span></th>`;
        for (const y of years) {
          const v = M.val(corp, fs, y, stmt, n.id);
          html += `<td>${cellButton(corp, fs, y, stmt, n.id, v, unit, perShare)}</td>`;
        }
        html += "</tr>";
      }
      html += "</tbody>";
    }
    $("#dart-table").innerHTML = html;
    const nHidden = ch.order.filter((id) => !has(id)).length;
    $("#dart-empty-note").textContent = state.showEmpty ? "" : `이 회사·구분에서 세 해 모두 값이 없는 표준 계정 ${nHidden}개는 숨겼습니다.`;
  }
  function cellButton(corp, fs, y, stmt, sid, v, unit, perShare) {
    const a = `data-corp="${corp}" data-fs="${fs}" data-year="${y}" data-stmt="${stmt}" data-sid="${sid}"`;
    if (!v) return `<button type="button" class="v absent" ${a} aria-label="${y} 값 없음, 설명 보기">없음</button>`;
    const tag = v.source === "rollup" ? '<span class="src" title="하위 계정의 합">합</span>' : v.source === "formula" ? '<span class="src" title="공식으로 계산">식</span>' : "";
    const lab = { reported: "보고값", rollup: "하위 계정 합", formula: "공식 값" }[v.source];
    return `<button type="button" class="v${v.value < 0 ? " neg" : ""}" ${a} data-value="${v.value}" data-source="${v.source}" aria-label="${y} ${fmt(v.value, unit, perShare)} ${unitLabel(unit, perShare)}, ${lab}, 출처 보기">${tag}${fmt(v.value, unit, perShare)}</button>`;
  }

  // ------------------------------------------------------------ 2. 출처 패널
  const prov = { stack: [], opener: null };
  function openProv(args, push) {
    if (push && prov.cur) prov.stack.push(prov.cur);
    if (!push) prov.stack = [];
    prov.cur = args;
    const p = M.provenance(args.corp, args.fs, args.year, args.stmt, args.sid);
    const panel = $("#dart-prov");
    $("#prov-title").textContent = `${p.node.name}`;
    $("#prov-body").innerHTML = provHtml(p);
    $("#prov-back").hidden = !prov.stack.length;
    panel.hidden = false;
    $("#dart-backdrop").hidden = false;
    document.body.classList.add("prov-open");
    $("#prov-body").scrollTop = 0;
    panel.focus();
  }
  function closeProv() {
    const panel = $("#dart-prov");
    if (panel.hidden) return;
    panel.hidden = true;
    $("#dart-backdrop").hidden = true;
    document.body.classList.remove("prov-open");
    prov.stack = []; prov.cur = null;
    if (prov.opener && document.contains(prov.opener)) prov.opener.focus();
  }
  function amt(v, perShare, cls) {
    if (v === null || v === undefined) return '<span class="absent">없음</span>';
    const u = state.unit;
    const main = `${fmt(v, u, perShare)} <span class="u">${unitLabel(u, perShare)}</span>`;
    const exact = perShare || u === "won" ? "" : `<span class="exact">${fmtWon(v)} 원</span>`;
    return `<span class="amt ${cls || ""}">${main}${exact}</span>`;
  }
  function nodeLink(p, sid, label) {
    return `<button type="button" class="link" data-go="${sid}">${esc(label)}</button>`;
  }
  function provHtml(p) {
    const n = p.node, v = p.v, ps = n.kind === "per_share";
    let h = `<p class="prov-ctx">${esc(p.company)} · ${FS[p.fs]} · ${p.year} 사업보고서 · ${STMT[p.stmt]}</p>`;
    h += `<div class="prov-node"><div><code>${esc(n.id)}</code> <span class="kind">${KIND[n.kind] || n.kind}</span>${n.parent ? ` · 상위: ${nodeLink(p, n.parent, M.charts[p.stmt].nodes.get(n.parent).name)}` : ""}</div>` +
      `<div class="en">${esc(n.en)}</div>${n.note ? `<div class="note">차트 설명: ${esc(n.note)}</div>` : ""}` +
      (n.formula ? `<div class="note">공식: <code>${esc(n.formula)}</code></div>` : "") + "</div>";
    if (!v) {
      h += `<div class="prov-value"><span class="absent big">없음</span></div>`;
      h += `<h3>왜 값이 없나</h3><p>이 보고서에는 이 표준 계정에 대응하는 줄이 없고, ${n.kind === "formula" ? "공식에 필요한 값도 모두 있지는 않습니다" : "하위 계정에도 값이 없습니다"}. 0 이 아니라 <b>값이 없는 것</b>입니다.</p>`;
      if (n.kind === "formula") {
        h += "<ul class='plain'>" + n.terms.map(([t]) => {
          const tv = M.val(p.corp, p.fs, p.year, p.stmt, t);
          return `<li>${nodeLink(p, t, M.charts[p.stmt].nodes.get(t).name)}: ${tv ? amt(tv.value) : '<span class="absent">없음</span>'}</li>`;
        }).join("") + "</ul>";
      }
      if (p.ancestor) {
        const an = M.charts[p.stmt].nodes.get(p.ancestor.sid);
        h += `<p class="hint">이 회사는 이 금액을 상위 계정 ${nodeLink(p, an.id, an.name)} 안에 포함해 보고합니다 (${an.name} ${fmt(p.ancestor.v.value, state.unit)} ${UNITS[state.unit].label}).</p>`;
      }
      h += filingHtml(p);
      return h;
    }
    h += `<div class="prov-value">${amt(v.value, ps, "big")}</div>`;
    h += "<h3>값을 얻은 방법</h3>";
    if (v.source === "reported") {
      h += `<p>회사가 보고한 줄 ${p.reported.length === 1 ? "하나를 그대로" : `${p.reported.length}개를 더해`} 썼습니다${p.reported.some((l) => l.flip < 0) ? " (부호 반대로 공시한 줄은 −1 을 곱함)" : ""}.</p>`;
      if (v.roll !== null) {
        const same = v.roll === v.rep;
        h += `<p class="${same ? "ok" : "bad"}">하위 계정을 더한 값 ${amt(v.roll)} 과 ${same ? "원 단위까지 같습니다 ✓" : `다릅니다 (차이 ${fmtWon(v.rep - v.roll)} 원)`}.</p>`;
      }
    } else if (v.source === "rollup") {
      h += "<p>회사가 이 계정을 한 줄로 보고하지 않아, 값이 있는 하위 계정을 부호에 맞춰 더했습니다.</p>";
    } else {
      h += `<p>공식 <code>${esc(n.formula)}</code> 로 계산했습니다 (회사가 보고한 값은 없음).</p>`;
    }
    if (v.source === "reported") h += linesHtml(p.reported, "보고한 줄", v.rep, ps);
    if (p.parts && (v.roll !== null)) h += partsHtml(p, v);
    if (v.roll !== null && p.rollLeaves.length) {
      h += `<details class="leaves"><summary>${n.kind === "formula" ? "공식" : "하위 합계"}에 실제로 들어간 원본 줄 ${p.rollLeaves.length}개</summary>` +
        leafTable(p, v.roll) + "</details>";
    }
    if (p.checkOnly.length) {
      h += "<h3>점검용으로만 쓴 줄</h3><p class='small'>다른 곳에 이미 있는 값을 다시 적은 줄입니다. 더하지 않고, 노드 값과 같은지만 확인합니다.</p>";
      h += linesHtml(p.checkOnly, null, null, ps, true);
    }
    if (p.checks.length) {
      h += "<h3>이 노드의 대사 점검</h3><ul class='plain checks'>" + p.checks.map((c) =>
        `<li class="${c.status}"><b>${STATUS[c.status] || c.status}</b> ${esc(c.check)}${c.diff ? ` (차이 ${fmtWon(c.diff)} 원)` : ""}</li>`).join("") + "</ul>";
    }
    h += filingHtml(p);
    return h;
  }
  function linesHtml(lines, title, total, ps, checkOnly) {
    let h = title ? `<h3>${title} (as-reported)</h3>` : "";
    h += '<ol class="lines">';
    for (const l of lines) {
      h += `<li class="line" data-raw-index="${l.raw_index}" data-amount="${l.amount}" data-flip="${l.flip}" data-role="${l.role}">` +
        `<div class="ln-head"><span class="ln-name">${esc(l.account_nm)}</span>${amt(l.amount * l.flip, ps)}</div>` +
        `<dl>` +
        `<dt>XBRL 계정</dt><dd>${l.account_id ? `<code>${esc(l.account_id)}</code>` : "표준계정코드 미사용"}</dd>` +
        `<dt>재무제표</dt><dd>${SJ[l.sj] || l.sj}</dd>` +
        `<dt>공시 금액</dt><dd>${fmtWon(l.amount)} ${ps ? "원/주" : "원"}${l.flip < 0 ? ` <span class="flag">부호 반대로 공시 → × −1</span>` : ""}</dd>` +
        `<dt>매핑</dt><dd>${METHOD[l.method] || esc(l.method)} · 신뢰도 ${CONF[l.confidence] || esc(l.confidence)} · ${REVIEW[l.review] || esc(l.review)}` +
        `${l.role === "check_only" ? ' · <span class="flag">check_only</span>' : ""}${l.map_year ? ` · ${l.map_year} 보고서 전용 매핑` : ""}${l.occurrence > 1 ? ` · 같은 이름의 ${l.occurrence}번째 줄` : ""}</dd>` +
        (l.note ? `<dt>매핑 메모</dt><dd>${esc(l.note)}</dd>` : "") +
        `<dt>원본 위치</dt><dd class="small">raw_index ${l.raw_index}</dd>` +
        `</dl></li>`;
    }
    h += "</ol>";
    if (total !== null && total !== undefined && lines.length > 1 && !checkOnly) h += `<p class="sum">합계 = ${amt(total, ps)}</p>`;
    return h;
  }
  function partsHtml(p, v) {
    const isF = p.node.kind === "formula";
    let h = `<h3>${isF ? "공식의 구성" : "하위 계정"} ${v.source === "reported" ? "(대사용)" : ""}</h3><table class="parts"><tbody>`;
    for (const x of p.parts) {
      if (!x.v) {
        if (!state.showEmpty) continue;
      }
      const cn = M.charts[p.stmt].nodes.get(x.sid);
      h += `<tr class="${x.v ? "" : "na"}"><td class="sg">${x.sign < 0 ? "−" : "+"}</td><td>${nodeLink(p, x.sid, cn.name)}${x.v && x.v.source !== "reported" ? ` <span class="src">${x.v.source === "rollup" ? "합" : "식"}</span>` : ""}</td>` +
        `<td class="r" data-part="${x.sid}" data-sign="${x.sign}" data-value="${x.v ? x.v.value : ""}">${x.v ? amt(x.v.value) : '<span class="absent">없음</span>'}</td></tr>`;
    }
    const missing = p.parts.filter((x) => !x.v).length;
    h += `<tr class="tot"><td class="sg">=</td><td>${esc(p.node.name)}</td><td class="r">${amt(v.roll)}</td></tr></tbody></table>`;
    if (missing && !isF) h += `<p class="small">값이 없는 하위 계정 ${missing}개는 더하지 않았습니다 (0 으로 채우지 않음).</p>`;
    return h;
  }
  function leafTable(p, total) {
    let h = '<table class="parts leaf"><tbody>';
    for (const x of p.rollLeaves) {
      h += `<tr data-raw-index="${x.line.raw_index}" data-amount="${x.line.amount}" data-eff-sign="${x.sign * x.line.flip}"><td class="sg">${x.sign < 0 ? "−" : "+"}</td>` +
        `<td>${esc(x.line.account_nm)}<span class="small"> → ${esc(M.charts[p.stmt].nodes.get(x.via).name)}${x.line.flip < 0 ? " · 부호 반대로 공시해 × −1" : ""}</span></td><td class="r">${amt(x.line.amount * x.line.flip)}</td></tr>`;
    }
    h += `<tr class="tot"><td class="sg">=</td><td>합계</td><td class="r">${amt(total)}</td></tr></tbody></table>`;
    return h;
  }
  function filingHtml(p) {
    const f = p.filing;
    if (!f) return "<h3>공시</h3><p>이 회사·연도·구분의 보고서가 없습니다.</p>";
    return `<h3>공시</h3><dl class="filing"><dt>보고서</dt><dd>${esc(f.report_nm || "사업보고서")}</dd>` +
      `<dt>접수번호</dt><dd><code>${esc(f.rcept_no)}</code></dd><dt>공시일</dt><dd>${ymd(f.rcept_dt)}</dd>` +
      `<dt>원본 파일</dt><dd class="small"><code>${esc(f.raw_file)}</code></dd></dl>` +
      `<p><a class="ext" href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${encodeURIComponent(f.rcept_no)}" target="_blank" rel="noopener noreferrer">DART 에서 원문 보기 ↗</a></p>`;
  }

  // ------------------------------------------------------------ 3. 회사 간 비교
  function nodeOptions(filter) {
    const q = (filter || "").trim().toLowerCase();
    let h = "";
    for (const stmt of ["BS", "PL"]) {
      const ch = M.charts[stmt];
      const ids = stmt === "BS" ? sections("BS")[0].rows.map((r) => [r.sid, r.depth])
        : sections("PL").flatMap((s) => s.rows.map((r) => [r.sid, r.depth]));
      const opts = ids.filter(([id]) => {
        if (!q) return true;
        const n = ch.nodes.get(id);
        return n.name.toLowerCase().includes(q) || id.toLowerCase().includes(q) || n.en.toLowerCase().includes(q);
      }).map(([id, dep]) => `<option value="${id}"${id === state.cmp ? " selected" : ""}>${"  ".repeat(dep)}${esc(ch.nodes.get(id).name)}</option>`);
      if (opts.length) h += `<optgroup label="${STMT[stmt]}">${opts.join("")}</optgroup>`;
    }
    return h;
  }
  function renderCompare() {
    const sid = state.cmp, fs = state.cmpFs, stmt = M.stmtOf(sid), unit = state.unit;
    const node = M.charts[stmt].nodes.get(sid);
    const ps = node.kind === "per_share";
    const sel = $("#cmp-node");
    if (sel.value !== sid) sel.innerHTML = nodeOptions($("#cmp-search").value);
    const years = M.years;
    let html = `<caption class="sr-only">${esc(node.name)} ${FS[fs]}, 회사별·연도별 (${unitLabel(unit, ps)})</caption>`;
    html += `<thead><tr><th scope="col">회사 <span class="unit-note">${unitLabel(unit, ps)}</span></th>` + years.map((y) => `<th scope="col">${y}</th>`).join("") + "</tr></thead><tbody>";
    const series = [];
    let nAll = 0, nAny = 0;
    const hints = [];
    for (const [corp, name] of M.companies) {
      html += `<tr><th scope="row">${esc(name)}</th>`;
      const vals = years.map((y) => M.val(corp, fs, y, stmt, sid));
      vals.forEach((v, i) => { html += `<td>${cellButton(corp, fs, years[i], stmt, sid, v, unit, ps)}</td>`; });
      html += "</tr>";
      series.push({ corp, name, vals });
      if (vals.every(Boolean)) nAll++;
      if (vals.some(Boolean)) nAny++;
      const missYears = years.filter((y, i) => !vals[i]);
      if (missYears.length) hints.push(hintFor(corp, name, fs, stmt, sid, missYears));
    }
    $("#cmp-table").innerHTML = html + "</tbody>";
    $("#cmp-coverage").innerHTML = `<b>${esc(node.name)}</b> <code>${esc(sid)}</code> (${FS[fs]}): 5개사 중 <b>${nAll}개사</b>가 세 해 모두 값이 있습니다` +
      (nAny > nAll ? `, ${nAny - nAll}개사는 일부 연도만` : "") + "." + (node.note ? ` <span class="small">${esc(node.note)}</span>` : "");
    $("#cmp-hints").innerHTML = hints.map((h) => `<li>${h}</li>`).join("");
    barChart($("#cmp-chart"), series, years, unit, ps, node.name, fs, stmt, sid);
  }
  function hintFor(corp, name, fs, stmt, sid, missYears) {
    const ch = M.charts[stmt], node = ch.nodes.get(sid);
    const y = missYears[missYears.length - 1];
    const yrs = missYears.length === M.years.length ? "" : ` (${missYears.join(", ")})`;
    if (node.kind === "formula") {
      const miss = node.terms.filter(([t]) => !M.val(corp, fs, y, stmt, t)).map(([t]) => ch.nodes.get(t).name);
      return `${esc(name)}: ${esc(node.name)} 없음${yrs} — 공식에 필요한 ${esc(miss.join(", "))}이(가) 없습니다.`;
    }
    let p = node.parent;
    while (p) {
      if (M.val(corp, fs, y, stmt, p)) {
        return `${esc(name)}: ${esc(node.name)} 없음${yrs} — 이 회사는 상위 계정 <b>${esc(ch.nodes.get(p).name)}</b>에서만 값이 있습니다 (그 안에 포함해 보고).`;
      }
      p = ch.nodes.get(p).parent;
    }
    return `${esc(name)}: ${esc(node.name)} 없음${yrs} — 이 보고서에 대응하는 줄이 없습니다.`;
  }

  function svgEl(name, attrs, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceStep(span, target) {
    const raw = span / Math.max(1, target);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / mag;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  }
  function barChart(container, series, years, unit, ps, title, fs, stmt, sid) {
    container.innerHTML = "";
    const div = ps ? 1 : UNITS[unit].div;
    const w = Math.max(300, container.clientWidth - 16);
    const narrow = w < 560;
    const h = narrow ? 300 : 340;
    const m = { l: narrow ? 52 : 64, r: 10, t: 16, b: 40 };
    const all = series.flatMap((s) => s.vals.filter(Boolean).map((v) => v.value / div));
    let lo = Math.min(0, ...all), hi = Math.max(0, ...all);
    if (lo === hi) hi = lo + 1;
    const step = niceStep(hi - lo, 5);
    lo = Math.floor(lo / step + 1e-9) * step; hi = Math.ceil(hi / step - 1e-9) * step;
    if (lo === hi) hi += step;
    const Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (h - m.t - m.b);
    const svg = svgEl("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": `${title} 회사별 막대그래프` }, container);
    const g = svgEl("g", {}, svg);
    const dec = step < 1 ? Math.min(4, Math.ceil(-Math.log10(step))) : 0;
    for (let v = lo; v <= hi + step * 1e-6; v += step) {
      const vv = +v.toFixed(10);
      svgEl("line", { x1: m.l, x2: w - m.r, y1: Y(vv), y2: Y(vv), class: vv === 0 ? "axis-line" : "grid-line" }, g);
      const t = svgEl("text", { x: m.l - 6, y: Y(vv) + 4, "text-anchor": "end" }, g);
      t.textContent = vv.toLocaleString("ko-KR", { minimumFractionDigits: dec, maximumFractionDigits: dec }).replace("-", "−");
    }
    const t0 = svgEl("text", { x: m.l, y: m.t - 4, class: "axis-title" }, g);
    t0.textContent = unitLabel(unit, ps);
    const gw = (w - m.l - m.r) / series.length;
    const bw = Math.min(26, (gw - 14) / years.length);
    const colors = ["--y1", "--y2", "--y3"];
    series.forEach((s, i) => {
      const x0 = m.l + i * gw + (gw - bw * years.length) / 2;
      s.vals.forEach((v, k) => {
        const x = x0 + k * bw;
        if (!v) {          // 값 없음: 막대 대신 점선 자리표시 (0 막대와 구별)
          svgEl("rect", { x: x + 2, y: Y(0) - 10, width: Math.max(2, bw - 4), height: 10, class: "absent-mark" }, g);
          if (bw >= 22 && !s.vals.every((z) => !z)) {
            const t = svgEl("text", { x: x + bw / 2, y: Y(0) - 14, "text-anchor": "middle", class: "absent-label" }, g);
            t.textContent = "없음";
          }
          return;
        }
        const yv = v.value / div;
        const y1 = Y(Math.max(0, yv)), y2 = Y(Math.min(0, yv));
        const r = svgEl("rect", { x: x + 1, y: y1, width: Math.max(1, bw - 2), height: Math.max(1, y2 - y1), style: `fill:var(${colors[k]})`, class: "bar",
          tabindex: "-1", "data-corp": s.corp, "data-year": years[k] }, g);
        r.addEventListener("click", () => { prov.opener = document.querySelector(`#cmp-table button[data-corp="${s.corp}"][data-year="${years[k]}"]`); openProv({ corp: s.corp, fs, year: years[k], stmt, sid }); });
        r.addEventListener("pointermove", (ev) => Charts.showTip(`<div class="t">${esc(s.name)} ${years[k]}</div><div class="r"><span>${esc(title)}</span><b>${fmt(v.value, unit, ps)} ${unitLabel(unit, ps)}</b></div>`, ev.clientX, ev.clientY));
        r.addEventListener("pointerleave", () => Charts.hideTip());
      });
      if (s.vals.every((z) => !z)) {
        const t = svgEl("text", { x: m.l + i * gw + gw / 2, y: Y(0) - 16, "text-anchor": "middle", class: "absent-label" }, g);
        t.textContent = "없음";
      }
      const lab = svgEl("text", { x: m.l + i * gw + gw / 2, y: h - m.b + 16, "text-anchor": "middle" }, g);
      lab.textContent = narrow ? (SHORT[s.name] || s.name) : s.name;
    });
    const lg = document.createElement("div");
    lg.className = "legend";
    lg.innerHTML = years.map((y, k) => `<span><i class="dot sq" style="background:var(${colors[k]})"></i>${y}</span>`).join("") +
      '<span class="small">막대를 누르면 출처를 봅니다. 점선 칸 = 값 없음 (0 이 아님).</span>';
    container.insertBefore(lg, container.firstChild);
  }

  // ------------------------------------------------------------ 4. 검증 상태
  function renderStatus() {
    const S = D.summary;
    const line = (name, label) => {
      const s = S[name], st = s.status;
      const extra = [];
      if (st.fail) extra.push(`실패 ${st.fail}건`);
      if (st.missing) extra.push(`값 없음 ${st.missing}건`);
      if (st.one_side) extra.push(`한쪽만 있음 ${st.one_side}건 (재작성 비교에서 한쪽 보고서에만 값)`);
      return `<li><b>${label}</b>: 대사 점검 ${s.total.toLocaleString("ko-KR")}건 중 <b>${(st.pass || 0).toLocaleString("ko-KR")}건 통과</b>${extra.length ? ", " + extra.join(", ") : ", 실패 0건"}.</li>`;
    };
    const findings = ["BS", "PL"].flatMap((n) => S[n].findings);
    let h = `<h2>검증 상태</h2><ul class="plain">${line("BS", "재무상태표")}${line("PL", "손익")}</ul>`;
    if (findings.length) {
      h += "<p><b>알려진 발견</b></p><ul class='plain'>" + findings.map((f) =>
        `<li>${esc(f.company)} ${f.bsns_year} 보고서 ${FS[f.fs_div]} ${f.period === "current" ? "당기" : f.period === "prior" ? "전기" : "전전기"}(${esc(f.period_end.slice(0, 4))}) 열, ${esc(f.check)}: 차이 ${fmtWon(f.diff)} 원. ${f.known ? esc(f.known) : "<b>설명되지 않은 실패</b>"}</li>`).join("") + "</ul>";
    } else h += "<p>알려진 발견 없음.</p>";
    h += `<details class="defs"><summary>점검 종류별 보기</summary><div class="table-wrap"><table class="data small-t"><thead><tr><th scope="col">점검</th><th scope="col">통과</th><th scope="col">실패</th><th scope="col">값 없음</th><th scope="col">한쪽만</th></tr></thead><tbody>` +
      ["BS", "PL"].map((n) => `<tr class="sec"><th scope="rowgroup" colspan="5">${n === "BS" ? "재무상태표" : "손익"} (${esc(S[n].file)})</th></tr>` +
        S[n].by_check.map((r) => `<tr><td>${esc(r[0])}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td><td>${r[4]}</td></tr>`).join("")).join("") +
      "</tbody></table></div><p class='small'>점검은 당기·전기·전전기 열 모두에 대해 했습니다. 이 화면의 표는 각 해 보고서의 당기 열만 보여 줍니다. 원 단위로 정확히 같아야 통과입니다.</p></details>";
    $("#dart-status").innerHTML = h;
  }

  // ------------------------------------------------------------ 화면 연결
  function render() {
    $("#dart-view-company").hidden = state.view !== "company";
    $("#dart-view-compare").hidden = state.view !== "compare";
    document.querySelectorAll("#dart-views button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === state.view));
    document.querySelectorAll(".dart-unit").forEach((s) => { s.value = state.unit; });
    if (state.view === "company") renderCompany(); else renderCompare();
  }
  function wire() {
    const fc = $("#form-dart");
    const co = fc.elements.corp;
    co.innerHTML = M.companies.map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join("");
    state.corp = M.companies[0][0];
    fc.addEventListener("submit", (e) => e.preventDefault());
    fc.addEventListener("change", () => {
      state.corp = co.value; state.fs = fc.elements.fs.value; state.stmt = fc.elements.stmt.value;
      state.showEmpty = fc.elements.empty.checked;
      render();
    });
    document.querySelectorAll(".dart-unit").forEach((s) => s.addEventListener("change", () => { state.unit = s.value; render(); if (prov.cur) openProv(prov.cur, false); }));
    $("#dart-expand").addEventListener("click", () => { state.open[state.stmt] = new Set([...M.charts[state.stmt].nodes.values()].filter((n) => n.children.length).map((n) => n.id)); render(); });
    $("#dart-collapse").addEventListener("click", () => { state.open[state.stmt] = defaultOpen(state.stmt); render(); });
    document.querySelectorAll("#dart-views button").forEach((b) => b.addEventListener("click", () => { state.view = b.dataset.view; render(); }));
    const fm = $("#form-cmp");
    fm.addEventListener("submit", (e) => e.preventDefault());
    $("#cmp-node").innerHTML = nodeOptions("");
    $("#cmp-search").addEventListener("input", () => {
      const sel = $("#cmp-node");
      sel.innerHTML = nodeOptions($("#cmp-search").value);
      if (sel.options.length && !Array.from(sel.options).some((o) => o.value === state.cmp)) { state.cmp = sel.options[0].value; sel.value = state.cmp; renderCompare(); }
    });
    $("#cmp-node").addEventListener("change", () => { state.cmp = $("#cmp-node").value; renderCompare(); });
    fm.elements.fs.addEventListener("change", () => { state.cmpFs = fm.elements.fs.value; renderCompare(); });

    // 표: 접기/펼치기와 값 누르기 (이벤트 위임)
    for (const id of ["#dart-table", "#cmp-table"]) {
      $(id).addEventListener("click", (e) => {
        const t = e.target.closest("button");
        if (!t) return;
        if (t.classList.contains("tog")) {
          const set = state.open[state.stmt], sid = t.dataset.sid;
          if (set.has(sid)) set.delete(sid); else set.add(sid);
          renderCompany();
          const again = $(`#dart-table .tog[data-sid="${sid}"]`);
          if (again) again.focus();
          return;
        }
        if (t.classList.contains("v")) {
          prov.opener = t;
          openProv({ corp: t.dataset.corp, fs: t.dataset.fs, year: t.dataset.year, stmt: t.dataset.stmt, sid: t.dataset.sid }, false);
        }
      });
    }
    // 패널
    $("#prov-close").addEventListener("click", closeProv);
    $("#dart-backdrop").addEventListener("click", closeProv);
    $("#prov-back").addEventListener("click", () => { const a = prov.stack.pop(); if (a) { prov.cur = a; openProvNoPush(a); } });
    $("#prov-body").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-go]");
      if (!b) return;
      openProv(Object.assign({}, prov.cur, { sid: b.dataset.go }), true);
    });
    document.addEventListener("keydown", (e) => {
      const panel = $("#dart-prov");
      if (panel.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); closeProv(); return; }
      if (e.key === "Tab") {        // 패널 안에서만 이동
        const f = Array.from(panel.querySelectorAll("button:not([hidden]), a[href], summary")).filter((x) => x.offsetParent !== null);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }
  function openProvNoPush(a) {
    const p = M.provenance(a.corp, a.fs, a.year, a.stmt, a.sid);
    $("#prov-title").textContent = p.node.name;
    $("#prov-body").innerHTML = provHtml(p);
    $("#prov-back").hidden = !prov.stack.length;
    $("#dart-prov").focus();
  }

  // ------------------------------------------------------------ 불러오기
  let loading = null;
  function load() {
    if (D) return Promise.resolve();
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      if (root.DART) { resolve(); return; }
      const s = document.createElement("script");
      s.src = "dart-data.js";
      s.onload = () => (root.DART ? resolve() : reject(new Error("데이터가 비어 있습니다")));
      s.onerror = () => reject(new Error("dart-data.js 를 불러오지 못했습니다"));
      document.head.appendChild(s);
    }).then(() => {
      D = root.DART;
      M = buildModel(D);
      api.model = M;
      $("#dart-loading").hidden = true;
      $("#dart-main").hidden = false;
      renderStatus();
      wire();
    }).catch((e) => { $("#dart-loading").textContent = e.message; $("#dart-loading").classList.add("error"); throw e; });
    return loading;
  }
  let lastW = 0;
  function show() {
    load().then(() => {
      const w = window.innerWidth;
      if (!api.shown || state.view === "compare" && w !== lastW) render();
      api.shown = true; lastW = w;
    }).catch(() => {});
  }
  const api = { show, load, state, render, openProv, closeProv, model: null, shown: false, fmt };
  root.DartView = api;
})(window);
