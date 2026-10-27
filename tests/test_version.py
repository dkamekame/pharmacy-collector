from datetime import date

import pytest

from collector.config import VersionToken
from collector.errors import VersionError
from collector.extract import Link
from collector.version import determine_version, parse_as_of, parse_href_token

REIWA = VersionToken(pattern=r"_r(?P<reiwa>\d{2})(?P<month>\d{2})\.", era="reiwa")
WESTERN2 = VersionToken(pattern=r"^(?P<yy>\d{2})(?P<month>\d{2})-\d{2}-\d{2}\.", era="western2")


@pytest.mark.parametrize("text, expected", [
    ("令和8年10月1日現在", date(2026, 10, 1)),
    ("令和８年１０月１日 現在", date(2026, 10, 1)),
    ("令和元年5月1日現在", date(2019, 5, 1)),
    ("平成31年4月1日現在", date(2019, 4, 1)),
    ("令和8年13月1日現在", None),
    ("2026年10月1日現在", None),
])
def test_parse_as_of(text, expected):
    assert parse_as_of(text) == expected


@pytest.mark.parametrize("url, token, expected", [
    ("https://x/kantoshinetsu/shitei_yakkyoku_r0810.zip", REIWA, (2026, 10)),
    ("https://x/tokaihokuriku/2610-01-04.zip", WESTERN2, (2026, 10)),
    ("https://x/tokaihokuriku/2701-01-04.zip", WESTERN2, (2027, 1)),
    ("https://x/tokaihokuriku/2613-01-04.zip", WESTERN2, None),
    ("https://x/kantoshinetsu/shitei_yakkyoku.zip", REIWA, None),
])
def test_parse_href_token(url, token, expected):
    assert parse_href_token(url, token) == expected


def test_page_date_and_href_agree():
    v = determine_version(Link("https://x/2610-01-04.zip", "薬局", "令和8年10月1日現在"), WESTERN2)
    assert (v.month, v.as_of, v.warnings) == ("2026-10", "2026-10-01", ())


def test_mismatch_prefers_page_date_and_warns():
    v = determine_version(Link("https://x/2609-01-04.zip", "薬局", "令和8年10月1日現在"), WESTERN2)
    assert v.month == "2026-10"
    assert "一致しません" in v.warnings[0]


def test_falls_back_to_href_when_page_date_missing():
    v = determine_version(Link("https://x/2610-01-04.zip", "薬局", None), WESTERN2)
    assert (v.month, v.as_of) == ("2026-10", None)
    assert "基準日" in v.warnings[0]


def test_fails_when_neither_available():
    with pytest.raises(VersionError):
        determine_version(Link("https://x/yakkyoku.zip", "薬局", None), WESTERN2)
