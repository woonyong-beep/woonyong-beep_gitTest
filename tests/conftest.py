"""테스트 공통 설정: 저장소 루트를 import 경로에 넣고, 테스트 중 네트워크 접근을 막는다."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """collectors.http.get 을 부르면 바로 실패하게 한다. 필요한 테스트는 따로 바꿔 끼운다."""
    from collectors import http

    def blocked(*a, **k):
        raise AssertionError("테스트에서 네트워크 요청을 시도함")
    monkeypatch.setattr(http, "get", blocked)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
