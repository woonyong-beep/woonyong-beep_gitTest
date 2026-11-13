"""OpenDART 엔드포인트별 함수. 모두 캐시를 거친다 (캐시가 있으면 네트워크를 쓰지 않는다).

- corp_codes(): corpCode.xml (zip 안의 CORPCODE.xml) -> [{corp_code, corp_name, stock_code, modify_date}]
- company(): company.json 기업개황
- filings(): list.json 공시검색 (여러 쪽이면 모두 받는다)
- fnltt_all(): fnlttSinglAcntAll.json 단일회사 전체 재무제표
- document(): document.xml 공시서류원본파일 (zip)
- xbrl(): fnlttXbrl.xml 재무제표 원본파일 XBRL (zip)
- taxonomy(): xbrlTaxonomy.json XBRL 택사노미 재무제표 양식
"""

import io
import xml.etree.ElementTree as ET
import zipfile

from . import paths

REPORT_CODES = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서", "11014": "3분기보고서"}


def corp_codes(client):
    data = client.get_bytes("corpCode.xml", {}, paths.corp_code_zip())
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read(z.namelist()[0])
    return parse_corp_codes(xml)


def parse_corp_codes(xml_bytes):
    out = []
    for el in ET.fromstring(xml_bytes).iter("list"):
        out.append({k: (el.findtext(k) or "").strip()
                    for k in ("corp_code", "corp_name", "stock_code", "modify_date")})
    return out


def company(client, corp_code):
    return client.get_json("company.json", {"corp_code": corp_code}, paths.company_json(corp_code))


def filings(client, corp_code, bgn_de, end_de, pblntf_ty="A"):
    """공시 목록 전체 (쪽을 모두 모은다). 반환: (rows, cache_files)."""
    rows, files, page = [], [], 1
    while True:
        params = {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de, "pblntf_ty": pblntf_ty,
                  "page_count": "100", "page_no": str(page)}
        path = paths.list_json(corp_code, bgn_de, end_de, pblntf_ty, page)
        obj = client.get_json("list.json", params, path)
        files.append(path)
        rows.extend(obj.get("list", []))
        if page >= int(obj.get("total_page", 1) or 1):
            return rows, files
        page += 1


def fnltt_all(client, corp_code, year, reprt_code, fs_div):
    params = {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": reprt_code, "fs_div": fs_div}
    path = paths.fnltt_json(corp_code, year, reprt_code, fs_div)
    return client.get_json("fnlttSinglAcntAll.json", params, path), path


def document(client, rcept_no):
    path = paths.document_zip(rcept_no)
    return client.get_bytes("document.xml", {"rcept_no": rcept_no}, path), path


def xbrl(client, rcept_no, reprt_code):
    path = paths.xbrl_zip(rcept_no)
    return client.get_bytes("fnlttXbrl.xml", {"rcept_no": rcept_no, "reprt_code": reprt_code}, path), path


def taxonomy(client, sj_div):
    return client.get_json("xbrlTaxonomy.json", {"sj_div": sj_div}, paths.taxonomy_json(sj_div))
