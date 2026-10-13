"""A body geckodriver does not accept is refused in serde's words, with the
place where the reading stopped in the JSON Selenium sends.

Every expected message below was answered by the original - Selenium 4.51,
geckodriver 0.37.1 and retail Firefox 151 - on 2026-10-13, to the same
call. Until 0.4.0 these were InvalidArgumentException with words of our own,
`str()` of a name that was not a string, and NoSuchFrameException for an
index geckodriver refuses before Marionette sees it.
"""
from __future__ import annotations

import pytest

from invisible_selenium import _serde
from invisible_selenium.common import exceptions as exc

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("cookie, message", [
    ({"name": 1, "value": "1"},
     "invalid type: integer `1`, expected a string at line 1 column 21"),
    ({"value": "1"}, "missing field `name` at line 1 column 25"),
    ({"name": "e", "value": "1", "expiry": 1.5e9},
     "invalid type: floating point `1500000000.0`, expected u64 at line 1 column 61"),
    ({"name": "e", "value": "1", "secure": None},
     "invalid type: null, expected a boolean at line 1 column 53"),
    ({"name": ["a"], "value": "1"},
     "invalid type: sequence, expected a string at line 1 column 20"),
    ({"name": {"a": 1}, "value": "1"},
     "invalid type: map, expected a string at line 1 column 20"),
    ({"value": 2, "name": 3},
     "invalid type: integer `2`, expected a string at line 1 column 22"),
    ({"name": None, "value": "1"},
     "invalid type: null, expected a string at line 1 column 24"),
    ({"name": "a", "value": "1", "path": 5},
     "invalid type: integer `5`, expected a string at line 1 column 48"),
    ({"name": "a", "value": "1", "secure": 1},
     "invalid type: integer `1`, expected a boolean at line 1 column 50"),
    ({"name": "a", "value": "1", "expiry": -1},
     "invalid value: integer `-1`, expected u64 at line 1 column 51"),
    ({"name": "a", "value": "1", "expiry": "5"},
     'invalid type: string "5", expected u64 at line 1 column 52'),
    (["name", "value"],
     "invalid length 2, expected struct AddCookieParameters with 8 elements "
     "at line 1 column 28"),
    ({"name": "a", "value": 7, "path": 'x"y'},
     "invalid type: integer `7`, expected a string at line 1 column 35"),
], ids=lambda v: v if isinstance(v, str) and "column" not in v else None)
def test_a_cookie_geckodriver_refuses(cookie, message):
    with pytest.raises(exc.InvalidArgumentException) as caught:
        _serde.check_cookie(cookie)
    assert caught.value.msg == message


@pytest.mark.parametrize("cookie", [
    {"name": "pn", "value": "1", "path": None},
    {"name": "xk", "value": "1", "foo": [1, 2]},
    {"name": "a", "value": "1", "expiry": 2 ** 53},
])
def test_a_cookie_geckodriver_takes(cookie):
    _serde.check_cookie(cookie)


@pytest.mark.parametrize("reference, column", [(-1, 10), (70000, 13), (True, 12),
                                               (1.5, 11)])
def test_a_frame_id_no_variant_matches(reference, column):
    error = _serde.untagged("FrameId", {"id": reference})
    assert error.msg == ("data did not match any variant of untagged enum "
                         "FrameId at line 1 column %d" % column)


def test_a_window_type_that_is_not_a_string():
    with pytest.raises(exc.InvalidArgumentException) as caught:
        _serde.check_string_or_null("type", 1)
    assert caught.value.msg == ("invalid type: integer `1`, expected a string "
                                "at line 1 column 10")
    _serde.check_string_or_null("type", "foo")
    _serde.check_string_or_null("type", None)


@pytest.mark.parametrize("using, column", [("foo", 15), ("", 12)])
def test_a_locator_strategy_geckodriver_does_not_know(using, column):
    error = _serde.unknown_strategy(using)
    assert error.msg == (
        "unknown variant `%s`, expected one of `css selector`, `link text`, "
        "`partial link text`, `tag name`, `xpath` at line 1 column %d"
        % (using, column))
