"""`execute_script` is sent once, whatever happens to its document [B285].

A world that went under a script does not say whether the script ran: Juggler
sends a message still waiting for its answer again to the document that
replaces the one it went to, so a script waiting on a promise when its page
navigated is refused in the same words as one that never ran, and the engine's
other answer ("Execution context was destroyed!") says outright that it ran.
0.3.6 sent a refused script again into the new document, which ran it twice.
Marionette never sends `executeScript` again and answers null
(`NO_RETRY_METHODS`, `MarionetteCommandsParent.sys.mjs`).

The core's REAL `InjectedScript` runs here, over a transport that answers a
call aimed at a context that has gone with Juggler's own words, so what turns
those answers into `ContextDestroyed` is the core's `_send_in` and nothing
imitates it.
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

_REFUSED = "Failed to find execution context with id = %s"
_INTERRUPTED = "Execution context was destroyed!"


class _Transport(EventListeners):
    """`Runtime.callFunction` answers in a live context; in a context that has
    gone it answers with the engine's text, and the first such answer also
    brings the new document's world, as a navigation committing in between
    would."""

    def __init__(self):
        super().__init__()
        self.calls = []
        self.gone = {}
        #: The script answers an object, and its document goes before the
        #: object's properties are read.
        self.answer_then_go = False

    def send(self, method, params=None, session=None, timeout=30):
        if method == "Runtime.disposeObject":
            return {}
        context = params["executionContextId"]
        if method == "Runtime.getObjectProperties" and self.answer_then_go:
            raise ProtocolError(
                'Runtime.getObjectProperties: exception while running method '
                '"getObjectProperties" in namespace "page": ' + _REFUSED % context)
        assert method == "Runtime.callFunction", method
        self.calls.append(context)
        if context in self.gone:
            self.world("new")
            text = self.gone[context]
            if "%s" in text:
                text %= context
            raise ProtocolError(
                'Runtime.callFunction: exception while running method '
                '"callFunction" in namespace "page": ' + text)
        if self.answer_then_go:
            return {"result": {"objectId": "answer", "type": "object"}}
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


@pytest.mark.parametrize("answer", [_REFUSED, _INTERRUPTED],
                         ids=["refused", "interrupted"])
def test_a_script_whose_document_went_is_null_and_not_sent_again(answer):
    driver, transport = _driver()
    transport.gone["old"] = answer
    assert driver.execute_script("localStorage.runs++") is None
    assert transport.calls == ["old"]


def test_a_script_in_a_live_document_runs_once():
    driver, transport = _driver()
    assert driver.execute_script("return 1") == "ran in old"
    assert transport.calls == ["old"]


def test_a_script_carrying_an_element_of_a_document_that_went_is_stale(monkeypatch):
    driver, transport = _driver()
    transport.gone["old"] = _REFUSED
    # The element crossed into the old document's world: an objectId there.
    monkeypatch.setattr(_bridge.Marshal, "arguments",
                        lambda self, values: ([{"objectId": "el-1"}], False))
    with pytest.raises(exc.StaleElementReferenceException):
        driver.execute_script("return arguments[0]", object())
    assert transport.calls == ["old"]


def test_a_script_that_ran_and_whose_document_went_before_its_answer_was_read_is_null():
    """The answer is read back in the world it was made in; gone, the script
    ran and its answer cannot come back: null, as Marionette answers a script
    whose window went, and it is not sent again."""
    driver, transport = _driver()
    transport.answer_then_go = True
    assert driver.execute_script("return {a: 1}") is None
    assert transport.calls == ["old"]
