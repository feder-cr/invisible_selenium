"""The seam between Selenium's API and the engine, without a browser."""
from __future__ import annotations

import pytest

from invisible_selenium import _bridge
from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.keys import Keys

pytestmark = pytest.mark.unit


def test_locators_are_rewritten_the_way_seleniums_client_does():
    assert _bridge.css_for("id", "x") == ("css selector", '[id="x"]')
    assert _bridge.css_for("name", "q") == ("css selector", '[name="q"]')
    assert _bridge.css_for("class name", "big") == ("css selector", ".big")
    assert _bridge.css_for("tag name", "a") == ("css selector", "a")
    assert _bridge.css_for("xpath", "//a") == ("xpath", "//a")
    assert _bridge.css_for("link text", "Go") == ("link text", "Go")


def test_every_key_constant_maps_to_a_layout_key_or_is_refused_by_name():
    from invisible_selenium._juggler.keyboard import Keyboard
    kb = Keyboard(connection=None, session="s")
    for attr in dir(Keys):
        if attr.startswith("_"):
            continue
        ch = getattr(Keys, attr)
        if not isinstance(ch, str) or len(ch) != 1 or ch == Keys.NULL:
            continue
        try:
            name = _bridge.key_name(ch)
        except exc.InvalidArgumentException:
            assert ch in ("\ue001", "\ue002", "\ue005", "\ue026", "\ue040"), attr
            continue
        if name == "Space":
            continue
        kb.describe(name)  # raises UnknownKey if the layout lacks it


class _FakeKeyboard:
    def __init__(self):
        self.log = []
        self.modifiers = set()

    def down(self, name):
        self.log.append(("down", name))
        self.modifiers.add(name)

    def up(self, name):
        self.log.append(("up", name))
        self.modifiers.discard(name)

    def press(self, name):
        self.log.append(("press", name))


class _FakeActions:
    def __init__(self):
        self.keyboard = _FakeKeyboard()
        self.typed = []

    def _type(self, text):
        self.typed.append(text)
        self.keyboard.log.append(("type", text))


def test_send_keys_modifiers_are_sticky_until_sent_again_null_or_the_end():
    a = _FakeActions()
    _bridge.type_keys(a, Keys.CONTROL + "a" + Keys.NULL + "bc" + Keys.SHIFT + "d",
                      sticky=True)
    assert a.keyboard.log == [
        ("down", "Control"), ("press", "a"), ("up", "Control"),
        ("type", "bc"), ("down", "Shift"), ("press", "d"), ("up", "Shift")]


def test_action_chain_keys_are_pressed_one_by_one():
    a = _FakeActions()
    _bridge.type_keys(a, "ab" + Keys.ENTER + Keys.SHIFT, sticky=False)
    assert a.keyboard.log == [("type", "ab"), ("press", "Enter"),
                              ("press", "Shift")]


def test_space_is_typed_with_its_neighbours():
    a = _FakeActions()
    _bridge.type_keys(a, "a" + Keys.SPACE + "b", sticky=True)
    assert a.typed == ["a b"]


def test_a_held_modifier_is_released_even_when_typing_fails():
    class BoomKeyboard(_FakeKeyboard):
        def press(self, name):
            raise RuntimeError("pipe closed")
    a = _FakeActions()
    a.keyboard = BoomKeyboard()
    with pytest.raises(RuntimeError):
        _bridge.type_keys(a, Keys.SHIFT + "x", sticky=True)
    assert a.keyboard.log[0] == ("down", "Shift")
    assert a.keyboard.log[-1] == ("up", "Shift")


def test_flat_script_arguments_run_the_callers_body_and_nothing_else():
    decl = _bridge.script_declaration("return arguments[0]", False, is_async=False)
    assert decl == "function() {\nreturn arguments[0]\n}"


def test_async_scripts_append_the_callback_without_calling_array_methods():
    decl = _bridge.script_declaration("arguments[0]()", False, is_async=True)
    assert "new Promise" in decl and "__a[__a.length] = __r" in decl
    assert ".push(" not in decl and ".slice(" not in decl


def test_nested_elements_use_the_placeholder_rebuild():
    decl = _bridge.script_declaration("return 1", True, is_async=False)
    assert "__invisible_selenium_element__" in decl


def test_engine_failures_become_seleniums_exceptions():
    from invisible_selenium._juggler.connection import TargetClosedError
    from invisible_selenium._juggler.injected import EvaluationError
    assert isinstance(_bridge.translate(EvaluationError("x")),
                      exc.JavascriptException)
    assert isinstance(_bridge.translate(RuntimeError("Cannot find object with id = 3")),
                      exc.StaleElementReferenceException)
    assert isinstance(_bridge.translate(TimeoutError("<element> not actionable: missing visible")),
                      exc.ElementNotInteractableException)
    assert isinstance(_bridge.translate(TargetClosedError("gone")),
                      exc.NoSuchWindowException)
    already = exc.NoSuchElementException("x")
    assert _bridge.translate(already) is already


class _FakeInjected:
    """Just enough of InjectedScript for Marshal.result."""

    def __init__(self, props):
        self.props = props
        self.released = []

    def main_context(self, frame_id):
        return "ctx"

    def properties(self, ctx, oid):
        return self.props[oid]

    def by_value(self, ctx, oid):
        return "by-value:" + oid

    def release(self, ctx, oid):
        self.released.append(oid)


class _FakePage:
    def __init__(self, injected):
        self.injected = injected


def test_results_are_read_back_through_object_properties():
    inj = _FakeInjected({
        "arr": [{"name": "0", "value": {"value": 1}},
                {"name": "1", "value": {"objectId": "obj", "type": "object"}},
                {"name": "length", "value": {"value": 2}}],
        "obj": [{"name": "a", "value": {"value": "x"}},
                {"name": "getter", "value": {}},
                {"name": "n", "value": {"unserializableValue": "NaN"}}],
        "list": [{"name": "1", "value": {"value": "second"}},
                 {"name": "0", "value": {"value": "first"}},
                 {"name": "item", "value": {"objectId": "f", "type": "function"}},
                 {"name": "length", "value": {}}],
    })
    m = _bridge.Marshal(driver=None, page=_FakePage(inj), frame_id="F")
    assert m.result({"objectId": "arr", "type": "object", "subtype": "array"}) == [
        1, {"a": "x", "n": None}]
    assert m.result({"objectId": "list", "type": "object"}) == ["first", "second"]
    assert m.result({"objectId": "d", "type": "object", "subtype": "date"}) == "by-value:d"
    assert m.result({"value": None}) is None
    assert m.result({"unserializableValue": "-0"}) == 0
    m.release()
    assert set(inj.released) >= {"arr", "obj", "list", "d"}


def test_a_cycle_is_refused_instead_of_walked_forever():
    inj = _FakeInjected({"loop": [{"name": "self",
                                   "value": {"objectId": "loop", "type": "object"}}]})
    m = _bridge.Marshal(driver=None, page=_FakePage(inj), frame_id="F")
    with pytest.raises(exc.JavascriptException):
        m.result({"objectId": "loop", "type": "object"})
