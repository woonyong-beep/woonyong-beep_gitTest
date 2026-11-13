"""공시서류 원본(document.xml zip) 시험 추출기: 연결 재무상태표만.

시험용(probe)이다. 최근 문서와 오래된 문서 모두에 같은 코드를 그대로 써 보는 것이 목적이라,
최근 문서에만 있는 인라인 XBRL 표시(TE 의 ACODE 속성)는 쓰지 않고 표의 글자만 읽는다.

원본 문서의 모양 (확인한 것)
- zip 안에 <접수번호>.xml (본문) 과 <접수번호>_00760.xml, _00761.xml (첨부: 감사보고서, 연결감사보고서) 가 있다.
  2015년 문서는 zip 안 파일 이름이 '/' 로 시작한다. 디스크에 풀지 않고 zip 에서 바로 읽는다.
- 마크업은 DART 전용 XML (dart3.xsd / dart4.xsd): SECTION-1/2/3, TITLE, TABLE-GROUP, TABLE/TR/TD·TH·TE·TU, P.
- XML 선언은 utf-8 이지만 실제로는 EUC-KR(cp949) 인 문서가 있다 (2003, 2015년 문서). 그래서 utf-8 로 먼저 읽고
  실패하면 cp949 로 읽는다.
"""

import html
import io
import re
import zipfile

UNITS = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "억원": 100_000_000}
_SPACE = re.compile(r"[\s　\xa0]+")
_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<TR\b[^>]*>(.*?)</TR>", re.S | re.I)
_CELL = re.compile(r"<(TD|TH|TE|TU)\b([^>]*)>(.*?)</\1>", re.S | re.I)
_COLSPAN = re.compile(r'COLSPAN="(\d+)"', re.I)


def decode(data):
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp949", errors="replace"), "cp949"


def read_zip(data):
    """zip bytes -> [(이름, 글자 수, 인코딩, 본문)]. 이름 앞의 '/' 는 떼어 낸다."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            text, enc = decode(z.read(info.filename))
            out.append((info.filename.lstrip("/\\"), len(text), enc, text))
    return out


def main_text(files, rcept_no):
    for name, _, enc, text in files:
        if name == f"{rcept_no}.xml":
            return text, enc
    return files[0][3], files[0][2]


def cell_text(s):
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", s))).strip()


def norm(s):
    """비교용 이름: 공백 없애고, (주4,29) 같은 주석 번호와 앞 번호(Ⅰ. 1. 가.) 를 뗀다."""
    s = _SPACE.sub("", s)
    s = re.sub(r"\((주|Note)[^)]*\)", "", s)
    s = re.sub(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[0-9]+|[가-하])[.)]", "", s)
    return s.strip("[]<>")


def parse_amount(s):
    """'1,234' -> 1234, '(1,234)' / '△1,234' / '-1,234' -> -1234, 빈칸·'-' -> None. 숫자가 아니면 ValueError."""
    t = _SPACE.sub("", s)
    if t in ("", "-", "−", "―"):
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    if t[:1] in ("△", "▲", "-", "−"):
        neg, t = True, t[1:]
    t = t.replace(",", "")
    if not re.fullmatch(r"\d+", t):
        raise ValueError(s)
    return -int(t) if neg else int(t)


def table_rows(table_html):
    rows = []
    for tr in _TR.finditer(table_html):
        cells = []
        for m in _CELL.finditer(tr.group(1)):
            span = _COLSPAN.search(m.group(2))
            cells.append(cell_text(m.group(3)))
            cells.extend([""] * (int(span.group(1)) - 1 if span else 0))
        rows.append(cells)
    return rows


TITLE_RE = re.compile(r"연\s*결\s*(재\s*무\s*상\s*태\s*표|대\s*차\s*대\s*조\s*표)")


def find_consolidated_bs(text):
    """연결 재무상태표 표의 위치를 찾는다. 반환 dict(start, unit, unit_text, header, rows) 또는 None.

    규칙: 셀이나 제목의 글자가 정확히 '연결 재무상태표'(또는 '2-1. 연결 재무상태표', '연결대차대조표') 인 곳을
    차례로 보고, 그 뒤 3000자 안에 '(단위 : ...)' 가 있고, 그 다음 표의 첫 열에 '자산총계' 가 있는 첫 곳을 쓴다.
    """
    for m in TITLE_RE.finditer(text):
        # 앞뒤가 태그 경계인지 (본문 문장 속 언급은 건너뛴다)
        before = text[max(0, m.start() - 200):m.start()]
        after = text[m.end():m.end() + 50]
        head = before[before.rfind(">") + 1:] if ">" in before else before
        tail = after[:after.find("<")] if "<" in after else after
        label = norm(head + m.group(0) + tail)
        if not re.fullmatch(r"(\d+(-\d+)?\.?)?연결(재무상태표|대차대조표)", label):
            continue
        window = text[m.end():m.end() + 3000]
        u = re.search(r"\(\s*단\s*위\s*:\s*([^)]+?)\s*\)", window)
        if not u:
            continue
        unit_text = _SPACE.sub("", cell_text(u.group(1)))
        unit = UNITS.get(unit_text)
        pos = m.end() + u.end()
        t0 = text.find("<TABLE", pos)
        t1 = text.find("</TABLE>", t0)
        if t0 < 0 or t1 < 0:
            continue
        rows = table_rows(text[t0:t1])
        if not any(norm(r[0]) in ("자산총계", "자산합계") for r in rows if r):
            continue
        return {"start": m.start(), "unit": unit, "unit_text": unit_text, "header": rows[0] if rows else [],
                "rows": rows[1:]}
    return None


def extract_bs(text):
    """연결 재무상태표 행 list: {row_no, label, name_norm, indent, values(단위 곱한 원 금액 list), raw}."""
    found = find_consolidated_bs(text)
    if not found:
        return None, "연결 재무상태표 표를 찾지 못함"
    out, notes = [], []
    unit = found["unit"]
    if unit is None:
        notes.append(f"단위 '{found['unit_text']}' 를 모름 (금액을 곱하지 않음)")
        unit = 1
    for i, cells in enumerate(found["rows"]):
        if not cells or not cells[0]:
            continue
        label = cells[0]
        vals = []
        for c in cells[1:]:
            try:
                v = parse_amount(c)
            except ValueError:
                notes.append(f"행 {i} '{label}': 숫자 아닌 칸 {c!r}")
                v = None
            vals.append(None if v is None else v * unit)
        out.append({"row_no": i, "label": label, "name_norm": norm(label), "values": vals, "raw": cells[1:]})
    return {"rows": out, "unit_text": found["unit_text"], "header": found["header"], "notes": notes}, None


def compare_with_api(doc_rows, api_rows, ncols=3):
    """원문 행과 API BS 행(같은 접수번호, CFS)을 이름으로 짝지어 당기·전기·전전기 금액을 비교한다.

    ncols: 앞에서부터 몇 개 열(당기, 전기, 전전기)을 비교할지. 다른 해 보고서와 견줄 때 겹치는 열만 본다.
    같은 이름이 여럿이면(예: 유동/비유동 충당부채) 아직 안 쓴 것 중 당기 금액이 같은 것, 없으면 첫째를 고른다.
    반환 (비교 행 list, 요약 dict).
    """
    from .extract import amount
    pool = {}
    for r in api_rows:
        pool.setdefault(norm(r["account_nm"]), []).append(r)
    used, out = set(), []
    for d in doc_rows:
        has_num = any(v is not None for v in d["values"])
        cands = [r for r in pool.get(d["name_norm"], []) if id(r) not in used]
        cur = d["values"][0] if d["values"] else None
        pick = next((r for r in cands if amount(r, "thstrm_amount") == cur), cands[0] if cands else None)
        rec = {"row_no": d["row_no"], "label": d["label"], "doc_cur": cur,
               "doc_prev": d["values"][1] if len(d["values"]) > 1 else None,
               "doc_prev2": d["values"][2] if len(d["values"]) > 2 else None, "has_number": has_num,
               "api_account_id": "", "api_account_nm": "", "api_cur": None, "api_prev": None, "api_prev2": None,
               "result": ""}
        if pick is None:
            rec["result"] = "짝없음" if has_num else "숫자없는행"
        else:
            used.add(id(pick))
            rec.update(api_account_id=pick["account_id"], api_account_nm=pick["account_nm"],
                       api_cur=amount(pick, "thstrm_amount"), api_prev=amount(pick, "frmtrm_amount"),
                       api_prev2=amount(pick, "bfefrmtrm_amount"))
            same = ((rec["doc_cur"], rec["doc_prev"], rec["doc_prev2"])[:ncols]
                    == (rec["api_cur"], rec["api_prev"], rec["api_prev2"])[:ncols])
            rec["result"] = "일치" if same else "금액다름"
        out.append(rec)
    api_left = [r for r in api_rows if id(r) not in used]
    num = [r for r in out if r["has_number"]]
    summ = {"doc_rows": len(out), "doc_rows_with_number": len(num),
            "matched": sum(1 for r in num if r["result"] in ("일치", "금액다름")),
            "equal": sum(1 for r in num if r["result"] == "일치"),
            "differ": sum(1 for r in num if r["result"] == "금액다름"),
            "doc_unmatched": sum(1 for r in num if r["result"] == "짝없음"),
            "api_rows": len(api_rows), "api_unmatched": [(r["account_id"], r["account_nm"]) for r in api_left]}
    return out, summ
