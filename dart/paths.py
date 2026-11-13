"""data/dart/ 아래 파일 위치.

raw/        API 응답 그대로 (JSON). 커밋한다.
raw/_large/ 원문 zip, XBRL zip, corpCode zip. 커밋하지 않는다 (.gitignore). large_manifest.csv 에 목록을 남긴다.
extracted/  as-reported 긴 표 (statements.csv)
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "dart"
RAW = DATA / "raw"
LARGE = RAW / "_large"
EXTRACTED = DATA / "extracted"
WATCHLIST = ROOT / "dart_watchlist.csv"

STATEMENTS_CSV = EXTRACTED / "statements.csv"
FILINGS_CSV = EXTRACTED / "filings.csv"
LARGE_MANIFEST = DATA / "large_manifest.csv"
CHECKS_CSV = DATA / "checks.csv"
CHECKS_MD = DATA / "checks.md"
INVENTORY_CSV = DATA / "account_inventory.csv"


def rel(path):
    """저장소 루트 기준 상대 경로 문자열 (슬래시)."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def corp_code_zip():
    return LARGE / "corpCode.zip"


def company_json(corp_code):
    return RAW / "company" / f"{corp_code}.json"


def list_json(corp_code, bgn, end, ty, page):
    return RAW / "list" / f"{corp_code}_{ty}_{bgn}_{end}_p{page}.json"


def fnltt_json(corp_code, year, reprt_code, fs_div):
    return RAW / "fnltt" / corp_code / f"{year}_{reprt_code}_{fs_div}.json"


def document_zip(rcept_no):
    return LARGE / "document" / f"{rcept_no}.zip"


def xbrl_zip(rcept_no):
    return LARGE / "xbrl" / f"{rcept_no}.zip"


def taxonomy_json(sj_div):
    return RAW / "taxonomy" / f"{sj_div}.json"
