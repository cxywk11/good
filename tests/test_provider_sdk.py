from decimal import Decimal

import pytest
from jc.providers.base import OddsProvider
from jc.providers.parsing import decimal_odds, parse_line
from jc.time import parse_time


@pytest.mark.parametrize("raw,expected", [("-0.5/-1", "-0.75"), ("2.5", "2.5"), ("0/0.5", "0.25")])
def test_lines(raw, expected):
    assert parse_line(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["NaN", "inf", "bad", "0.13", "-0.5/1"])
def test_invalid_lines(raw):
    with pytest.raises(ValueError):
        parse_line(raw)


@pytest.mark.parametrize(
    "raw,fmt,expected",
    [
        ("1.82", "decimal", "1.82"),
        ("0.82", "hong_kong", "1.82"),
        ("-200", "american", "1.5"),
        ("3/2", "fractional", "2.5"),
    ],
)
def test_odds_formats(raw, fmt, expected):
    assert decimal_odds(raw, fmt) == Decimal(expected)


def test_strict_timezone_and_abstract_adapter():
    with pytest.raises(ValueError):
        parse_time("2026-09-30 18:00")
    with pytest.raises(TypeError):
        OddsProvider()
