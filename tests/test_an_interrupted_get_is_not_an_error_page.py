"""`get` waits through an interruption as geckodriver does, and names an error
page as an error page.

A navigation that another document replaces before it commits - the previous
page's own `location.replace`, a form submit, going back - or that the page
stops (`document.open()`, `window.stop()`) is waited through by Marionette's
classic `get`: its listener ends on the next document that loads after the page
unloaded, or at the page load timeout. Measured on Selenium 4.51, geckodriver
0.37.1 and retail Firefox 151 (`C:/tmp/b230/oracle_selenium_class.py`,
2026-10-14): returned in 0.3 s on the page the page sent itself to. Until 0.5.2
this raised WebDriverException in the words of WebDriver BiDi's
NavigationManager, "A new navigation interrupted an unfinished navigation",
which the classic `get` never says ([B302]). A load that failed is still
geckodriver's "Reached error page".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from invisible_core.juggler.lifecycle import (NavigationError, NavigationInterrupted,
                                              NavigationMark)
from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.remote.webdriver import WebDriver

pytestmark = pytest.mark.unit


def _driver(raised, waited):
    def goto(url, **kwargs):
        raise raised

    def wait_for_new_navigation(frame_id, since, state, timeout=None, **kwargs):
        waited.append((since.navigation, state, kwargs.get("replaced")))
        return "nav-2"

    page = SimpleNamespace(
        main_frame_id="main",
        lifecycle=SimpleNamespace(
            goto=goto, wait_for_new_navigation=wait_for_new_navigation,
            mark=lambda fid: NavigationMark("nav-2", 0, 0)))
    driver = object.__new__(WebDriver)
    driver._check_alert = lambda: None
    driver._current_page = lambda: page
    driver._timeouts = SimpleNamespace(page_load=5)
    return driver


def test_an_interruption_is_waited_through_to_the_document_after_ours():
    said = ('Navigation to "http://a/next" is interrupted by another '
            'navigation to "http://a/landed"')
    waited = []
    assert _driver(NavigationInterrupted(said, "nav-1"), waited).get("http://a/next") is None
    # The first navigation after OURS, which may have started already, and
    # any document that replaces it, as Marionette's listener follows one.
    assert waited == [("nav-1", "load", "follow")]


def test_a_stop_by_the_page_is_waited_through_the_same_way():
    waited = []
    assert _driver(NavigationError("NS_BINDING_ABORTED", "nav-1"), waited).get("http://a/next") is None
    assert waited == [("nav-1", "load", "follow")]


def test_an_aborted_load_is_still_an_error_page():
    with pytest.raises(exc.WebDriverException) as e:
        _driver(NavigationError("NS_ERROR_UNKNOWN_HOST", "nav-1"), []).get("http://nowhere/")
    assert e.value.msg == "Reached error page: NS_ERROR_UNKNOWN_HOST"
