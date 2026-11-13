"""수집기가 함께 쓰는 HTTP 요청 함수 (표준 라이브러리 urllib).

- 요청에는 개인 정보나 저장소 정보를 넣지 않는다. User-Agent 는 소스별로 정한 일반 문자열만 쓴다.
- 429 (요청 과다), 5xx, 연결 끊김은 지수적으로 기다렸다가 다시 시도한다.
- 테스트에서는 이 모듈의 get 을 바꿔 끼워 네트워크 없이 돌린다.
"""

import time
import urllib.error
import urllib.parse
import urllib.request

RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """소스에서 데이터를 받지 못했을 때. 메시지에 URL 과 원래 오류를 담는다."""


def build_url(base, params=None):
    if not params:
        return base
    return base + "?" + urllib.parse.urlencode(params, safe=",")


def get(url, headers=None, timeout=60, retries=4, backoff=2.0):
    """URL 을 GET 해서 bytes 를 돌려준다. 실패하면 FetchError."""
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            last = f"HTTP {e.code} {e.reason}: {body}"
            if e.code not in RETRY_STATUS:
                break
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            last = repr(e)
        if attempt < retries:
            time.sleep(backoff * 2 ** attempt)
    raise FetchError(f"{url} -> {last}")
