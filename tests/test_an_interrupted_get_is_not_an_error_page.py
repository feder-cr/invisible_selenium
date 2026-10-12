"""`get` names an interruption as one, and an error page as an error page.

Since invisible-core 41.36.0 a navigation that another document replaces
before it commits - the previous page's own `location.replace`, which Firefox
lets win - raises `NavigationInterrupted` at once, where it used to wait for
the page-load timeout. It is a `NavigationError`, and `get` worded every
`NavigationError` as "Reached error page", which is what geckodriver says for
a network error: nothing failed to load here. Firefox's own WebDriver fails
the navigation too ("A new navigation interrupted an unfinished navigation"),
so it is still a WebDriverException, in the core's words.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from invisible_core.juggler.lifecycle import NavigationError, NavigationInterrupted
from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.remote.webdriver import WebDriver

pytestmark = pytest.mark.unit


def _driver(raised):
    def goto(url, **kwargs):
        raise raised

    page = SimpleNamespace(main_frame_id="main",
                           lifecycle=SimpleNamespace(goto=goto))
    driver = object.__new__(WebDriver)
    driver._check_alert = lambda: None
    driver._current_page = lambda: page
    driver._timeouts = SimpleNamespace(page_load=5)
    return driver


def test_an_interruption_is_worded_as_one():
    said = ('Navigation to "http://a/next" is interrupted by another '
            'navigation to "http://a/landed"')
    with pytest.raises(exc.WebDriverException) as e:
        _driver(NavigationInterrupted(said)).get("http://a/next")
    assert e.value.msg == said


def test_an_aborted_load_is_still_an_error_page():
    with pytest.raises(exc.WebDriverException) as e:
        _driver(NavigationError("NS_ERROR_UNKNOWN_HOST")).get("http://nowhere/")
    assert e.value.msg == "Reached error page: NS_ERROR_UNKNOWN_HOST"
