"""The seam between Selenium's API and the engine.

Everything Selenium-shaped that is not a public class lives here: how a locator
becomes a DOM query, how a W3C key code point becomes a key the engine's
keyboard knows, how a script's arguments go into the page and its result comes
back, and how an engine failure becomes the exception Selenium documents.

⛔ WHERE THINGS RUN. Every DOM read and every query below runs in the UTILITY
world (`__ctx_aux__`), which sees the page's DOM through an Xray: the methods
it calls are the NATIVE ones, not whatever the site may have replaced, and no
read is accountable to a wrapped accessor. Only `execute_script` crosses into
the page's own world, because running code as the page is what the caller
asked for - and even there the result is read back from the privileged side,
never by running a serializer the page can observe.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from ._juggler.connection import ProtocolError, TargetClosedError
from ._juggler.injected import UTILITY_WORLD, EvaluationError
from .common import exceptions as exc

# ── locators ────────────────────────────────────────────────────────────────
#: The strategies Selenium's own client rewrites to CSS before they reach a
#: driver. Kept byte for byte, quirks included: `By.CLASS_NAME` with a space in
#: it becomes a descendant selector in Selenium too, and a caller who relied on
#: that must get the same answer here.
def css_for(by: str, value: str) -> Tuple[str, str]:
    if by == "id":
        return "css selector", '[id="%s"]' % value
    if by == "name":
        return "css selector", '[name="%s"]' % value
    if by == "class name":
        return "css selector", ".%s" % value
    if by == "tag name":
        return "css selector", value
    return by, value


#: Runs in the utility world. `root` is an element, a shadow root, or null for
#: the document. The answer is an array of elements, or a string naming why
#: there cannot be one.
FIND_JS = """(root, by, value) => {
  if (root && root.isConnected === false) return 'stale';
  const scope = root || document;
  const doc = scope.ownerDocument || scope;
  if (by === 'css selector') return Array.from(scope.querySelectorAll(value));
  if (by === 'xpath') {
    const r = doc.evaluate(value, scope, null, 7, null);
    const out = [];
    for (let i = 0; i < r.snapshotLength; i++) {
      const n = r.snapshotItem(i);
      if (n.nodeType !== 1) return 'notelement';
      out.push(n);
    }
    return out;
  }
  if (by === 'link text' || by === 'partial link text') {
    const out = [];
    for (const a of scope.querySelectorAll('a')) {
      const text = (a.innerText || '').trim();
      if (by === 'link text' ? text === value : text.includes(value)) out.push(a);
    }
    return out;
  }
  return 'strategy';
}"""


def query(page, frame_id: str, root: Optional[str], by: str, value: str) -> List[str]:
    """Every match, as utility-world objectIds, in document order.

    ⛔ ONE ROUND TRIP FOR THE QUERY AND ONE FOR THE LIST, whatever the number
    of matches. The array stays on the engine side and its members are read
    back with `Runtime.getObjectProperties`, instead of asking for match N one
    call at a time.
    """
    by, value = css_for(by, value)
    inj = page.injected
    ctx = inj.context_id(frame_id)
    args = [{"objectId": root} if root else {"value": None},
            {"value": by}, {"value": value}]
    try:
        remote = inj.call_raw(ctx, FIND_JS, args)
    except EvaluationError as e:
        raise exc.InvalidSelectorException(
            "Given %s expression %r is invalid: %s" % (by, value, e)) from None
    if "objectId" not in remote:
        reason = remote.get("value")
        if reason == "stale":
            raise exc.StaleElementReferenceException(
                "The element reference is stale; either its node has been "
                "removed from the document or the document has changed")
        if reason == "notelement":
            raise exc.InvalidSelectorException(
                "The result of the xpath expression %r is not an element" % value)
        raise exc.InvalidArgumentException("unknown locator strategy %r" % by)
    array = remote["objectId"]
    try:
        items = [p for p in inj.properties(ctx, array) if p["name"].isdigit()]
        items.sort(key=lambda p: int(p["name"]))
        return [p["value"]["objectId"] for p in items
                if (p.get("value") or {}).get("objectId")]
    finally:
        inj.release(ctx, array)


# ── keys ────────────────────────────────────────────────────────────────────
#: W3C code point -> the key name the engine's keyboard resolves. The code
#: points are the spec's; the names are the layout's (`keylayout.py`).
KEY_NAMES: Dict[str, str] = {
    "\ue003": "Backspace", "\ue004": "Tab", "\ue006": "Enter",
    "\ue007": "Enter", "\ue008": "Shift", "\ue009": "Control",
    "\ue00a": "Alt", "\ue00b": "Pause", "\ue00c": "Escape",
    "\ue00d": "Space", "\ue00e": "PageUp", "\ue00f": "PageDown",
    "\ue010": "End", "\ue011": "Home", "\ue012": "ArrowLeft",
    "\ue013": "ArrowUp", "\ue014": "ArrowRight", "\ue015": "ArrowDown",
    "\ue016": "Insert", "\ue017": "Delete", "\ue018": "Semicolon",
    "\ue019": "Equal",
    "\ue01a": "Numpad0", "\ue01b": "Numpad1", "\ue01c": "Numpad2",
    "\ue01d": "Numpad3", "\ue01e": "Numpad4", "\ue01f": "Numpad5",
    "\ue020": "Numpad6", "\ue021": "Numpad7", "\ue022": "Numpad8",
    "\ue023": "Numpad9",
    "\ue024": "NumpadMultiply", "\ue025": "NumpadAdd",
    "\ue027": "NumpadSubtract", "\ue028": "NumpadDecimal",
    "\ue029": "NumpadDivide",
    "\ue031": "F1", "\ue032": "F2", "\ue033": "F3", "\ue034": "F4",
    "\ue035": "F5", "\ue036": "F6", "\ue037": "F7", "\ue038": "F8",
    "\ue039": "F9", "\ue03a": "F10", "\ue03b": "F11", "\ue03c": "F12",
    "\ue03d": "Meta",
    "\ue050": "ShiftRight", "\ue051": "ControlRight", "\ue052": "AltRight",
    "\ue053": "MetaRight",
}

#: The W3C modifier keys: sticky inside one `send_keys`, released at its end.
MODIFIER_KEYS = {"Shift", "Control", "Alt", "Meta", "ShiftRight",
                 "ControlRight", "AltRight", "MetaRight"}

NULL_KEY = "\ue000"


def is_special(ch: str) -> bool:
    return "\ue000" <= ch <= "\uf8ff"


def key_name(ch: str) -> str:
    name = KEY_NAMES.get(ch)
    if name is None:
        # ⛔ REFUSED, not skipped. Cancel, Help, Clear, Separator and
        # Zenkaku/Hankaku have no key on the US layout the engine carries, and
        # inventing one would send an event with an empty `code` - the tell the
        # keyboard module exists to avoid.
        raise exc.InvalidArgumentException(
            "key U+%04X has no key on the keyboard layout this browser "
            "presents" % ord(ch))
    return name


def _code_of(keyboard, ch: str) -> str:
    """The physical key that types `ch` on the layout, or `ch` itself."""
    describe = getattr(keyboard, "describe", None)
    if describe is None:
        return ch
    try:
        return describe(ch).get("code") or ch
    except Exception:
        return ch


def type_keys(actions, text: str, *, sticky: bool) -> None:
    """Deliver `text` through the engine keyboard, W3C style.

    Runs of ordinary characters are TYPED, so they get the session's typing
    rhythm; a code point from `Keys` is a key press. With `sticky` (element
    `send_keys`), a modifier stays down until it is sent again, until NULL, or
    until the end of the call; without it (ActionChains `send_keys`), every key
    is pressed and released on its own.
    """
    keyboard = actions.keyboard
    held: List[str] = []
    run: List[str] = []

    def flush():
        if not run:
            return
        if getattr(keyboard, "modifiers", None):
            # ⛔ A HELD MODIFIER CHANGES WHAT A KEY TYPES: Shift + "c" is "C"
            # and Control + "a" selects everything. Typing the run as text
            # would ignore the modifier, so each character is pressed on its
            # own and the keyboard resolves it against what is held.
            # The KEY is pressed, by its physical code, so the layout decides
            # what it types under the modifier - W3C's shifted character.
            for ch in run:
                keyboard.press(_code_of(keyboard, ch))
        else:
            actions._type("".join(run))
        run.clear()

    try:
        for ch in text:
            if not is_special(ch):
                run.append(ch)
                continue
            name = None if ch == NULL_KEY else key_name(ch)
            if name == "Space":
                # A space is a character: it stays inside the typed run, so
                # the words around it keep one rhythm.
                run.append(" ")
                continue
            flush()
            if name is None:
                for held_name in reversed(held):
                    keyboard.up(held_name)
                held.clear()
                continue
            if sticky and name in MODIFIER_KEYS:
                if name in held:
                    keyboard.up(name)
                    held.remove(name)
                else:
                    keyboard.down(name)
                    held.append(name)
                continue
            keyboard.press(name)
        flush()
    finally:
        for name in reversed(held):
            keyboard.up(name)


# ── errors ──────────────────────────────────────────────────────────────────
#: The engine's words for "the document this handle lived in is gone". For a
#: DRIVER read they mean "ask again, the new document is arriving"
#: (`is_context_gone`); for an ELEMENT they mean the element is stale.
_CONTEXT_GONE = ("Failed to find execution context", "Cannot find context",
                 "execution context was destroyed", "Execution context was destroyed")

_STALE_MARKS = _CONTEXT_GONE + ("Cannot find object",
                "not connected", "notconnected", "Node is detached",
                "can't access dead object", "has been destroyed")


def is_context_gone(error: BaseException) -> bool:
    text = str(error)
    return any(mark in text for mark in _CONTEXT_GONE)


def across_navigation(fn, *, timeout: float = 30.0):
    """Run a page-level read, again if a document change got in its way.

    ⛔ A NAVIGATION THE PAGE STARTED ON ITS OWN - a submitted form, a clicked
    link - replaces the frame's worlds, and for a moment the registry still
    names the old one: a read in that moment fails with "Failed to find
    execution context". That is not an answer about the page, it is the page
    being between two documents, so the read is repeated until the new world
    answers.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            return fn()
        except Exception as e:
            if not is_context_gone(e) or not poll(deadline, 0.05):
                raise


def translate(error: BaseException) -> BaseException:
    """The Selenium exception an engine failure stands for."""
    if isinstance(error, exc.WebDriverException):
        return error
    text = str(error)
    if isinstance(error, TargetClosedError):
        return exc.NoSuchWindowException(
            "Browsing context has been discarded: %s" % text)
    if any(mark in text for mark in _STALE_MARKS):
        return exc.StaleElementReferenceException(
            "The element reference is stale; either its node has been removed "
            "from the document or the document has changed: %s" % text)
    if isinstance(error, TimeoutError):
        if "missing visible" in text or "missing enabled" in text \
                or "missing editable" in text or "no quad" in text:
            return exc.ElementNotInteractableException(
                "Element could not be scrolled into view or is not "
                "interactable: %s" % text)
        if "hit" in text or "intercept" in text or "would receive" in text:
            return exc.ElementClickInterceptedException(text)
        return exc.TimeoutException(text)
    if isinstance(error, EvaluationError):
        return exc.JavascriptException(text)
    if isinstance(error, ProtocolError):
        if "no response in" in text:
            return exc.TimeoutException(text)
        return exc.WebDriverException(text)
    return exc.WebDriverException("%s: %s" % (type(error).__name__, text))


# ── script values ───────────────────────────────────────────────────────────
#: How deep a returned object is walked before it is called cyclic. A real
#: cycle never ends; nothing a script means to return is this deep.
MAX_DEPTH = 32
#: Past this many properties an object is not data, it is a host object like
#: `window`, and walking it is thousands of round trips for nothing.
MAX_PROPERTIES = 500
_ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


class Marshal:
    """Arguments into the page's world, and a result back out of it."""

    def __init__(self, driver, page, frame_id: str) -> None:
        self.driver = driver
        self.page = page
        self.frame_id = frame_id
        self.inj = page.injected
        self.ctx = self.inj.main_context(frame_id)
        self._owned: List[str] = []

    # arguments ────────────────────────────────────────────────────────────
    def _element_into_page(self, element) -> str:
        if element._page is not self.page or element._frame_id != self.frame_id:
            raise exc.StaleElementReferenceException(
                "The element belongs to another window or frame than the one "
                "the script runs in")
        element._check_alive()
        oid = self.inj.node_to_main(self.frame_id, element._oid)
        if not oid:
            raise exc.StaleElementReferenceException(
                "The element could not be passed to the page")
        self._owned.append(oid)
        return oid

    def arguments(self, values) -> Tuple[List[dict], bool]:
        """Protocol arguments, and whether any element sits INSIDE a list or a
        dict (which needs the placeholder path)."""
        from .webdriver.remote.webelement import WebElement

        nested: List[Any] = []

        def plain(v, top):
            if isinstance(v, WebElement):
                if top:
                    return {"objectId": self._element_into_page(v)}
                nested.append(v)
                return {"__invisible_selenium_element__": len(nested) - 1}
            if isinstance(v, (list, tuple)):
                return [plain(x, False) for x in v]
            if isinstance(v, dict):
                return {str(k): plain(x, False) for k, x in v.items()}
            return v

        args = []
        for v in values:
            converted = plain(v, True)
            args.append(converted if isinstance(converted, dict)
                        and "objectId" in converted else {"value": converted})
        if not nested:
            return args, False
        return ([{"value": [a.get("value") if "value" in a else None
                            for a in args]}]
                + [{"objectId": self._element_into_page(e)} for e in nested],
                True)

    # the result ───────────────────────────────────────────────────────────
    def result(self, remote: dict, depth: int = 0):
        from .webdriver.remote.webelement import WebElement

        if depth > MAX_DEPTH:
            raise exc.JavascriptException("Cyclic object value")
        if "unserializableValue" in remote:
            # JSON has no NaN or Infinity; W3C serialization turns them into
            # null, and -0 into 0.
            return 0 if remote["unserializableValue"] == "-0" else None
        oid = remote.get("objectId")
        if not oid:
            return remote.get("value")
        self._owned.append(oid)
        subtype = remote.get("subtype")
        kind = remote.get("type")
        if subtype == "null":
            return None
        if subtype == "node":
            adopted = self.inj.adopt(self.frame_id, None, oid)
            if not adopted:
                raise exc.StaleElementReferenceException(
                    "The script returned a node that could not be carried back")
            return WebElement(self.driver, self.page, self.frame_id, adopted)
        if kind == "function":
            return {}
        if subtype == "array":
            return self._list(oid, depth)
        if subtype in ("date", "regexp", "map", "set", "error", "typedarray",
                       "proxy", "weakmap", "weakset", "promise"):
            return self.inj.by_value(self.ctx, oid)
        props = self.inj.properties(self.ctx, oid)
        if len(props) > MAX_PROPERTIES:
            try:
                return self.inj.by_value(self.ctx, oid)
            except Exception:
                return None
        names = {p["name"] for p in props}
        if "item" in names and "length" in names:
            # NodeList / HTMLCollection: a list to Selenium, and their indexed
            # members are the only data they carry.
            return self._items(props, depth)
        out = {}
        for p in props:
            value = p.get("value") or {}
            if not value or ("objectId" not in value and "value" not in value
                             and "unserializableValue" not in value):
                continue  # an accessor: the Debugger reports no value
            out[p["name"]] = self.result(value, depth + 1)
        return out

    def _list(self, oid: str, depth: int):
        return self._items(self.inj.properties(self.ctx, oid), depth)

    def _items(self, props, depth: int):
        items = [p for p in props if p["name"].isdigit()]
        items.sort(key=lambda p: int(p["name"]))
        return [self.result(p.get("value") or {}, depth + 1) for p in items]

    def release(self) -> None:
        for oid in self._owned:
            self.inj.release(self.ctx, oid)
        self._owned.clear()


def script_declaration(body: str, nested: bool, *, is_async: bool) -> str:
    """The function the page runs for `execute_script`/`execute_async_script`.

    ⛔ THE BODY IS THE CALLER'S AND NOTHING ELSE RUNS IN THE PAGE when the
    arguments are flat, which is the ordinary case: the function is declared
    and called with them, and `arguments` inside is exactly what was passed.
    The placeholder rebuild below only exists for elements nested inside a list
    or a dict, and it walks nothing but the caller's own arguments.

    The newline before the closing brace lets a body end in a `//` comment.
    """
    inner = "function() {\n%s\n}" % body
    if is_async:
        # The callback Selenium appends as the last argument. Index assignment
        # rather than `push`: no method of the page's Array.prototype is called.
        call = ("function(...__a) { return new Promise((__r) => {"
                " __a[__a.length] = __r; (%s).apply(this, __a); }); }" % inner)
        if not nested:
            return call
        target = "(%s)" % call
    else:
        if not nested:
            return inner
        target = "(%s)" % inner
    return ("function(__spec, ...__els) {"
            " const __fill = (v) => {"
            "  if (v === null || typeof v !== 'object') return v;"
            "  if ('__invisible_selenium_element__' in v)"
            "   return __els[v.__invisible_selenium_element__];"
            "  for (const k in v) v[k] = __fill(v[k]);"
            "  return v; };"
            " return %s.apply(this, __fill(__spec)); }" % target)


def poll(deadline: float, interval: float = 0.1) -> bool:
    """Sleep one polling step if there is time left; False when there is not."""
    left = deadline - time.monotonic()
    if left <= 0:
        return False
    time.sleep(min(interval, left))
    return True


__all__ = ["css_for", "query", "type_keys", "translate", "Marshal",
           "script_declaration", "KEY_NAMES", "UTILITY_WORLD", "poll"]
