"""User-Agent明示・リクエスト間隔・リトライを担うHTTPクライアント。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .config import HttpConfig
from .errors import FetchError


@dataclass(frozen=True)
class Fetched:
    url: str        # リダイレクト後の最終URL（相対リンクの解決に使う）
    content: bytes


class PoliteClient:
    def __init__(self, cfg: HttpConfig, session: requests.Session | None = None,
                 sleep=time.sleep, clock=time.monotonic):
        self.cfg = cfg
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = cfg.user_agent
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    def get(self, url: str) -> Fetched:
        last_error = ""
        for attempt in range(self.cfg.retries + 1):
            if attempt:
                self._sleep(self.cfg.interval_sec * 2 ** attempt)
            self._wait_interval()
            try:
                resp = self.session.get(url, timeout=self.cfg.timeout_sec)
            except requests.exceptions.SSLError as e:
                # 証明書の問題は再試行しても直らない
                raise FetchError(
                    f"{url} のSSL証明書を検証できませんでした（社内プロキシのTLS検査環境なら"
                    f" REQUESTS_CA_BUNDLE の設定が必要です。README「トラブルシュート」参照）: {e}"
                ) from e
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = f"{type(e).__name__}: {e}"
                continue
            finally:
                self._last_request = self._clock()

            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            if resp.status_code >= 400:
                raise FetchError(f"{url} の取得に失敗しました（HTTP {resp.status_code}）")
            return Fetched(url=resp.url or url, content=resp.content)

        raise FetchError(f"{url} の取得に{self.cfg.retries + 1}回失敗しました（{last_error}）")

    def _wait_interval(self) -> None:
        if self._last_request is None:
            return
        remaining = self.cfg.interval_sec - (self._clock() - self._last_request)
        if remaining > 0:
            self._sleep(remaining)
