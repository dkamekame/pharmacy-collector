from types import SimpleNamespace

import pytest
import requests

from collector.config import HttpConfig
from collector.errors import FetchError
from collector.http import PoliteClient

CFG = HttpConfig(user_agent="test-agent/1.0", interval_sec=3, timeout_sec=5, retries=3)


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.headers = {}
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(status_code=outcome, content=b"ok", url=url)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def sleep(self, sec):
        self.slept.append(sec)
        self.now += sec

    def __call__(self):
        return self.now


def _client(outcomes):
    clock = FakeClock()
    session = FakeSession(outcomes)
    return PoliteClient(CFG, session=session, sleep=clock.sleep, clock=clock), session, clock


def test_sets_user_agent_and_waits_between_requests():
    client, session, clock = _client([200, 200])
    client.get("https://x/a")
    client.get("https://x/b")
    assert session.headers["User-Agent"] == "test-agent/1.0"
    assert clock.slept == [3]


def test_retries_5xx_and_connection_errors_with_backoff():
    client, session, clock = _client([503, requests.ConnectionError("reset"), 200])
    assert client.get("https://x/a").content == b"ok"
    assert session.calls == 3
    assert clock.slept[0] == 6   # 3秒 × 2^1


def test_gives_up_after_retries():
    client, session, _ = _client([500, 500, 500, 500])
    with pytest.raises(FetchError, match="4回失敗"):
        client.get("https://x/a")
    assert session.calls == 4


def test_4xx_is_not_retried():
    client, session, _ = _client([404])
    with pytest.raises(FetchError, match="HTTP 404"):
        client.get("https://x/a")
    assert session.calls == 1


def test_ssl_error_is_not_retried_and_explains_proxy():
    client, session, _ = _client([requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")])
    with pytest.raises(FetchError, match="REQUESTS_CA_BUNDLE"):
        client.get("https://x/a")
    assert session.calls == 1
