"""OpenDART API 클라이언트 (표준 라이브러리 urllib).

- 인증키는 환경 변수 DART_API_KEY 에서만 읽는다. 키는 crtfc_key 쿼리 인자로 보낸다.
- 키는 어디에도 남기지 않는다: 오류 메시지, 로그, 캐시 파일 이름, 저장하는 URL 은 모두 redact() 를 거친다.
- 받은 응답은 디스크에 캐시한다. 캐시 파일이 있으면 다시 받지 않는다 (OpenDART 는 하루 호출 한도가 있다).
- 429·5xx·연결 끊김은 지수적으로 기다렸다 다시 시도한다. JSON 응답의 status 가 020 (한도 초과) 이면 바로 멈춘다.
- 테스트에서는 이 모듈의 _urlopen 을 바꿔 끼운다 (tests/conftest.py 는 urllib.request.urlopen 을 막는다).
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://opendart.fss.or.kr/api/"
ENV_KEY = "DART_API_KEY"
RETRY_STATUS = {429, 500, 502, 503, 504}
PAUSE = 0.3          # 실제 요청 사이 최소 대기 (초)

# OpenDART status 코드 (개발가이드 기준)
STATUS_OK = "000"
STATUS_NO_DATA = "013"
STATUS_FATAL = {"010": "등록되지 않은 키", "011": "사용할 수 없는 키", "012": "접근할 수 없는 IP",
                "020": "요청 제한 초과", "021": "조회 가능한 회사 개수 초과", "100": "필드의 부적절한 값",
                "101": "부적절한 접근", "800": "시스템 점검", "900": "정의되지 않은 오류", "901": "개인정보 보유기간 만료"}

_KEY_PARAM = re.compile(r"(crtfc_key=)[^&\s\"'<>]*")


class DartError(RuntimeError):
    """OpenDART 요청이 실패했을 때. 메시지는 이미 redact 되어 있다."""


class DartFatal(DartError):
    """키 오류, 한도 초과처럼 계속해도 소용없는 오류."""


def api_key():
    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        raise DartFatal(f"환경 변수 {ENV_KEY} 가 없다. OpenDART 인증키가 필요하다.")
    return key


def redact(text, key=None):
    """문자열에서 인증키 값과 crtfc_key=... 를 지운다."""
    if text is None:
        return text
    text = str(text)
    if key is None:
        key = os.environ.get(ENV_KEY, "").strip()
    if key:
        text = text.replace(key, "***")
    return _KEY_PARAM.sub(r"\1***", text)


def public_url(endpoint, params):
    """기록용 URL. 키 자리는 *** 로 둔다."""
    rest = urllib.parse.urlencode({k: v for k, v in params.items() if k != "crtfc_key"})
    return BASE + endpoint + "?crtfc_key=***" + ("&" + rest if rest else "")


def _urlopen(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


class Client:
    """OpenDART 요청기. calls 는 이 객체가 실제로 네트워크에 보낸 요청 수 (캐시 적중 제외)."""

    def __init__(self, key=None, retries=4, backoff=2.0, timeout=90, pause=PAUSE):
        self._key = key
        self.retries, self.backoff, self.timeout, self.pause = retries, backoff, timeout, pause
        self.calls = 0
        self.cache_hits = 0
        self._last = 0.0

    @property
    def key(self):
        if self._key is None:
            self._key = api_key()
        return self._key

    def _fetch(self, endpoint, params):
        url = BASE + endpoint + "?" + urllib.parse.urlencode({"crtfc_key": self.key, **params})
        last = None
        for attempt in range(self.retries + 1):
            wait = self.pause - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (dart-collector)"})
            try:
                with _urlopen(req, self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                last = f"HTTP {e.code} {e.reason}: {body}"
                if e.code not in RETRY_STATUS:
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                last = repr(e)
            if attempt < self.retries:
                time.sleep(self.backoff * 2 ** attempt)
        raise DartError(redact(f"{public_url(endpoint, params)} -> {last}", self.key))

    def get_bytes(self, endpoint, params, cache_path=None):
        """응답 bytes. cache_path 가 있고 파일이 있으면 네트워크를 쓰지 않는다."""
        if cache_path is not None:
            cache_path = Path(cache_path)
            if cache_path.exists():
                self.cache_hits += 1
                return cache_path.read_bytes()
        data = self._fetch(endpoint, params)
        # 바이너리(zip) 응답 대신 오류 JSON/XML 이 오는 경우가 있다. 그때는 캐시하지 않고 오류로 올린다.
        check_error_body(data, endpoint, params)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(cache_path)
        return data

    def get_json(self, endpoint, params, cache_path=None):
        """JSON 응답 dict. status 000 과 013(데이터 없음) 만 캐시한다. 그 밖의 status 는 DartError."""
        if cache_path is not None and Path(cache_path).exists():
            self.cache_hits += 1
            return json.loads(Path(cache_path).read_text(encoding="utf-8"))
        data = self._fetch(endpoint, params)
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise DartError(redact(f"{public_url(endpoint, params)} -> JSON 아님: {e}", self.key))
        status = str(obj.get("status", ""))
        if status in STATUS_FATAL and status in {"010", "011", "012", "020", "021", "800", "901"}:
            raise DartFatal(redact(f"{endpoint}: status {status} {obj.get('message', '')}", self.key))
        if status not in (STATUS_OK, STATUS_NO_DATA):
            raise DartError(redact(f"{public_url(endpoint, params)} -> status {status} {obj.get('message', '')}",
                                   self.key))
        if cache_path is not None:
            cache_path = Path(cache_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(obj, ensure_ascii=False, indent=1)
            if self.key in text:   # 응답에 키가 섞여 들어오는 일은 없어야 하지만, 혹시 있으면 저장하지 않는다
                raise DartError("응답에 인증키 문자열이 들어 있어 저장하지 않음")
            cache_path.write_text(text + "\n", encoding="utf-8")
        return obj


def check_error_body(data, endpoint, params):
    """zip 을 기대한 요청에 오류 메시지(JSON 또는 XML)가 왔으면 DartError."""
    if data[:2] == b"PK":
        return
    head = data[:500].decode("utf-8", "replace")
    m = re.search(r'"status"\s*:\s*"(\d{3})"', head) or re.search(r"<status>(\d{3})</status>", head)
    if m:
        msg = re.search(r'"message"\s*:\s*"([^"]*)"', head) or re.search(r"<message>([^<]*)</message>", head)
        status = m.group(1)
        text = f"{endpoint}: status {status} {msg.group(1) if msg else ''}"
        if status in {"010", "011", "012", "020", "021", "800", "901"}:
            raise DartFatal(redact(text))
        raise DartError(redact(f"{public_url(endpoint, params)} -> {text}"))
