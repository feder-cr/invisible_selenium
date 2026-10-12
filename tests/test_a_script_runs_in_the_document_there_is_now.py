"""`execute_script` refused because its document had gone runs in the one there
is now, as Marionette sends it to the frame's current window.

Until 0.3.6 it raised a stale element: with the "none" page load strategy that
was every script sent while a page loaded. A script carrying an element is not
sent again, because the element belonged to the document that went.

The core's REAL `InjectedScript` runs here, over a transport that refuses a
call aimed at a context that has gone with Juggler's own words, so the rule
under test is the core's `in_current_world` and nothing imitates it.
"""
from __future__ import annotations

import pytest

from invisible_core.juggler.connection import EventListeners, ProtocolError
from invisible_core.juggler.injected import InjectedScript
from invisible_selenium import _bridge
from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.timeouts import Timeouts
from invisible_selenium.webdriver.remote.webdriver import WebDriver

pytestmark = pytest.mark.unit


class _Transport(EventListeners):
    """`Runtime.callFunction` answers in a live context and is refused in a
    dead one; the first call also brings the new document's world, as a
    navigation committing in between would."""

    def __init__(self):
        super().__init__()
        self.calls = []
        self.dead = set()

    def send(self, method, params=None, session=None, timeout=30):
        if method == "Runtime.disposeObject":
            return {}
        assert method == "Runtime.callFunction", method
        context = params["executionContextId"]
        self.calls.append(context)
        if context in self.dead:
            self.world("new")
            raise ProtocolError(
                "Failed to find execution context with id = %s" % context)
        return {"result": {"value": "ran in %s" % context}}

    def world(self, context):
        self.dispatch_event("Runtime.executionContextCreated",
                            {"executionContextId": context,
                             "auxData": {"frameId": "F"}}, "S")


class _Page:
    def __init__(self, injected):
        self.injected = injected


def _driver():
    transport = _Transport()
    page = _Page(InjectedScript(transport, "S"))
    transport.world("old")
    driver = WebDriver.__new__(WebDriver)
    driver._timeouts = Timeouts(script=5)
    driver._check_alert = lambda: None
    driver._current_page = lambda: page
    driver._frame_id = lambda: "F"
    return driver, transport


def test_a_refused_script_runs_in_the_new_document():
    driver, transport = _driver()
    transport.dead.add("old")
    assert driver.execute_script("return document.title") == "ran in new"
    assert transport.calls == ["old", "new"]


def test_a_script_in_a_live_document_runs_once():
    driver, transport = _driver()
    assert driver.execute_script("return 1") == "ran in old"
    assert transport.calls == ["old"]


def test_a_script_carrying_an_element_is_not_sent_again(monkeypatch):
    driver, transport = _driver()
    transport.dead.add("old")
    # The element crossed into the old document's world: an objectId there.
    monkeypatch.setattr(_bridge.Marshal, "arguments",
                        lambda self, values: ([{"objectId": "el-1"}], False))
    with pytest.raises(exc.StaleElementReferenceException):
        driver.execute_script("return arguments[0]", object())
    assert transport.calls == ["old"]
