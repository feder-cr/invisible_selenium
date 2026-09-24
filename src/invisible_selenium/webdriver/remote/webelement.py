"""`WebElement`, with Selenium's contract and the engine underneath.

⛔ AN ELEMENT HERE IS A NODE HELD IN THE UTILITY WORLD, not a reference the
page can see. Every read below is a function run in that world on the node,
so the DOM methods it calls are the native ones reached through the Xray; and
every action - click, typing, clearing, choosing an option - goes through the
engine's `Actions`, the same code invisible_playwright clicks with: a pointer
that travels, a press with a duration, keys with the session's rhythm, and
input events the browser marks as trusted.
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

from ... import _bridge
from ...common import exceptions as exc
from ...webdriver.common.by import By

#: What the retry loop prints when an action on this element times out: the
#: loop takes a selector for its message and never queries it once a node is
#: given, so this is a label.
_HANDLE = "<element>"

#: Selenium's getAttribute atom treats these as boolean attributes: the answer
#: is "true" or None, never the attribute's own text.
_BOOLEAN = frozenset("""allowfullscreen allowpaymentrequest allowusermedia async
autofocus autoplay checked compact complete controls declare default
defaultchecked defaultselected defer disabled ended formnovalidate hidden
indeterminate iscontenteditable ismap itemscope loop multiple muted nohref
nomodule noresize noshade novalidate nowrap open paused playsinline pubdate
readonly required reversed scoped seamless seeking selected truespeed
typemustmatch willvalidate""".split())

#: The atom's aliases from attribute name to property name.
_ALIASES = {"class": "className", "readonly": "readOnly"}

_GET_ATTRIBUTE_JS = """(el, name, booleans, aliases) => {
  const lower = name.toLowerCase();
  if (lower === 'style') return el.getAttribute('style');
  if ((lower === 'selected' || lower === 'checked') &&
      ('selected' in el || 'checked' in el)) {
    return (el.selected || el.checked) ? 'true' : null;
  }
  const tag = (el.localName || '').toLowerCase();
  if ((tag === 'img' && lower === 'src') || (tag === 'a' && lower === 'href')) {
    const raw = el.getAttribute(lower);
    return raw === null ? null : String(el[lower]);
  }
  const prop = aliases[lower] || name;
  if (booleans.includes(lower)) {
    const on = el.hasAttribute(lower) || !!el[prop];
    return on ? 'true' : null;
  }
  let value = el[prop];
  if (value === undefined || value === null || typeof value === 'object' ||
      typeof value === 'function') {
    value = el.getAttribute(name);
  }
  return value === undefined || value === null ? null : String(value);
}"""


class WebElement:
    """Represents a DOM element. Same methods and properties as Selenium's."""

    def __init__(self, parent, page, frame_id: str, oid: str) -> None:
        self._parent = parent
        self._page = page
        self._frame_id = frame_id
        self._oid = oid
        #: The utility world this node was taken in. A navigation replaces
        #: the world, and a node from the old one is stale by definition.
        self._ctx = page.injected.contexts.get((frame_id, _bridge.UTILITY_WORLD))
        import uuid
        self._id = str(uuid.uuid4())

    # ── identity ────────────────────────────────────────────────────────────
    @property
    def id(self) -> str:
        """Internal ID used by the driver for this element."""
        return self._id

    @property
    def parent(self):
        """The WebDriver instance this element was found from."""
        return self._parent

    @property
    def session_id(self) -> str:
        return self._parent.session_id

    def __repr__(self) -> str:
        return '<%s.%s (session="%s", element="%s")>' % (
            type(self).__module__, type(self).__name__, self.session_id,
            self._id)

    def __eq__(self, other) -> bool:
        """⛔ SAME NODE, NOT SAME REFERENCE. Two lookups of one node hand back
        two different engine handles, and Selenium's contract is that they
        compare equal; the question is asked in the utility world."""
        if not isinstance(other, WebElement):
            return False
        if other is self:
            return True
        if other._page is not self._page or other._frame_id != self._frame_id:
            return False
        try:
            return bool(self._call("(el, other) => el === other",
                                   {"objectId": other._oid}))
        except exc.StaleElementReferenceException:
            return False

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        # Consistent with __eq__: equal nodes are always in the same window
        # and frame, while two handles to one node have different ids.
        return hash((self._page.target_id, self._frame_id))

    # ── plumbing ────────────────────────────────────────────────────────────
    def _check_alive(self) -> None:
        self._parent._check_alert()
        if self._page.context is None or self._page not in self._page.context.pages:
            raise exc.NoSuchWindowException("the window of this element is closed")
        current = self._page.injected.contexts.get(
            (self._frame_id, _bridge.UTILITY_WORLD))
        if current is None or current != self._ctx:
            raise exc.StaleElementReferenceException(
                "The element reference is stale; either its node has been "
                "removed from the document or the document has changed")

    def _call(self, declaration: str, *args, by_value: bool = True):
        """Run `declaration(el, *args)` in the utility world, by value.

        A node that left the document is stale, and the check rides in the
        same round trip as the read.
        """
        self._check_alive()
        wrapped = ("(el, ...rest) => { if (!el.isConnected) return {s: 1};"
                   " return {v: (%s)(el, ...rest)}; }" % declaration)
        converted = [a if isinstance(a, dict) and ("objectId" in a or "value" in a)
                     else {"value": a} for a in args]
        try:
            remote = self._page.injected.call_raw(
                self._ctx, wrapped, [{"objectId": self._oid}] + converted,
                by_value=by_value)
        except Exception as e:
            raise _bridge.translate(e) from None
        value = remote.get("value") or {}
        if value.get("s"):
            raise exc.StaleElementReferenceException(
                "The element reference is stale; either its node has been "
                "removed from the document or the document has changed")
        return value.get("v")

    def _act(self, what, *args, **kwargs):
        """An engine action on this node, with Selenium's exceptions."""
        self._check_alive()
        actions = self._page.actions
        kwargs.setdefault("timeout", self._parent._action_timeout())
        try:
            return getattr(actions, what)(_HANDLE, *args, frame_id=self._frame_id,
                                          element_id=self._oid, **kwargs)
        except Exception as e:
            raise _bridge.translate(e) from None

    # ── reading ─────────────────────────────────────────────────────────────
    @property
    def tag_name(self) -> str:
        """This element's tagName property."""
        return self._call("(el) => (el.localName || el.tagName || '').toLowerCase()")

    @property
    def text(self) -> str:
        """The visible text of the element."""
        return self._call(
            "(el) => { const t = (typeof el.innerText === 'string')"
            " ? el.innerText : (el.textContent || ''); return t.trim(); }")

    def get_property(self, name) -> str | bool | WebElement | dict:
        """Gets the given property of the element."""
        self._check_alive()
        try:
            remote = self._page.injected.call_raw(
                self._ctx, "(el, name) => el[name]",
                [{"objectId": self._oid}, {"value": name}])
        except Exception as e:
            raise _bridge.translate(e) from None
        if remote.get("subtype") == "node":
            return WebElement(self._parent, self._page, self._frame_id,
                              remote["objectId"])
        if "objectId" in remote:
            try:
                return self._page.injected.by_value(self._ctx, remote["objectId"])
            finally:
                self._page.injected.release(self._ctx, remote["objectId"])
        return remote.get("value")

    def get_dom_attribute(self, name) -> str:
        """Gets the given attribute of the element, from the markup only."""
        # As W3C specifies, a boolean attribute answers "true" when present,
        # whatever its text, and None when absent.
        return self._call(
            "(el, name, booleans) => { const v = el.getAttribute(name);"
            " if (v !== null && booleans.includes(name.toLowerCase()))"
            " return 'true'; return v; }", name, sorted(_BOOLEAN))

    def get_attribute(self, name) -> str | None:
        """Gets the given attribute or property of the element.

        Same resolution as Selenium's getAttribute atom: boolean attributes
        answer "true" or None, `href`/`src` answer the resolved URL, and a
        property wins over the attribute of the same name when it is a
        primitive.
        """
        return self._call(_GET_ATTRIBUTE_JS, name, sorted(_BOOLEAN), _ALIASES)

    def is_selected(self) -> bool:
        """Whether the element is selected (checkboxes, radios, options)."""
        return bool(self._call("(el) => !!(el.selected || el.checked)"))

    def is_enabled(self) -> bool:
        """Returns whether the element is enabled."""
        return self._state("enabled")

    def is_displayed(self) -> bool:
        """Whether the element is visible to a user."""
        return self._state("visible")

    def _state(self, state: str) -> bool:
        self._check_alive()
        try:
            return bool(self._page.injected.element_state(
                self._frame_id, self._oid, state))
        except Exception as e:
            raise _bridge.translate(e) from None

    @property
    def rect(self) -> dict:
        """A dictionary with the size and location of the element, in document
        coordinates."""
        self._check_alive()
        try:
            box = self._page.injected.bounding_box(self._frame_id, self._oid)
        except Exception as e:
            raise _bridge.translate(e) from None
        scroll = self._call("(el) => ({x: el.ownerDocument.defaultView.scrollX,"
                            " y: el.ownerDocument.defaultView.scrollY})")
        if box is None:
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        return {"x": box["x"] + scroll["x"], "y": box["y"] + scroll["y"],
                "width": box["width"], "height": box["height"]}

    @property
    def location(self) -> dict:
        """The location of the element in the renderable canvas."""
        r = self.rect
        return {"x": round(r["x"]), "y": round(r["y"])}

    @property
    def size(self) -> dict:
        """The size of the element."""
        r = self.rect
        return {"height": r["height"], "width": r["width"]}

    @property
    def location_once_scrolled_into_view(self) -> dict:
        """Scrolls the element into view, then answers where it is on screen."""
        self._check_alive()
        try:
            self._page.injected.scroll_into_view(self._frame_id, self._oid)
            box = self._page.injected.bounding_box(self._frame_id, self._oid)
        except Exception as e:
            raise _bridge.translate(e) from None
        if box is None:
            return {"x": 0, "y": 0}
        return {"x": round(box["x"]), "y": round(box["y"])}

    def value_of_css_property(self, property_name) -> str:
        """The value of a CSS property, as computed."""
        return self._call(
            "(el, name) => el.ownerDocument.defaultView.getComputedStyle(el)"
            ".getPropertyValue(name)", property_name)

    @property
    def accessible_name(self) -> str:
        """The accessible name the browser computes for the element."""
        return self._call(
            "(el) => (el.getAttribute('aria-label') || el.innerText || "
            "el.getAttribute('alt') || el.getAttribute('title') || '').trim()")

    @property
    def aria_role(self) -> str:
        """The ARIA role of the element: its explicit role, else its tag's."""
        return self._call(
            "(el) => el.getAttribute('role') || (el.localName || '')")

    @property
    def shadow_root(self):
        """The element's OPEN shadow root.

        ⛔ Open only, which is Selenium's contract as well: a closed root is
        closed to the page's own code, and a driver that reached into it would
        be doing something no script on the page can do."""
        from .shadowroot import ShadowRoot

        self._check_alive()
        remote = self._page.injected.call_raw(
            self._ctx, "(el) => el.shadowRoot", [{"objectId": self._oid}])
        if "objectId" not in remote:
            raise exc.NoSuchShadowRootException(
                "This element does not have a shadow root")
        return ShadowRoot(self._parent, self._page, self._frame_id,
                          remote["objectId"])

    # ── acting ──────────────────────────────────────────────────────────────
    def click(self) -> None:
        """Clicks the element with the pointer, the way a person would.

        ⛔ AN <option> IS NOT CLICKED WITH THE POINTER, because inside a closed
        dropdown it has no box to land on. It is chosen through the engine's
        `select_option`, which fires `input` and `change` as trusted events -
        the same outcome Selenium's click on an option has. In a multiple
        select it toggles, which is also Selenium's behaviour.
        """
        info = self._call(
            "(el) => { if ((el.localName || '') !== 'option') return null;"
            " const s = el.closest('select'); if (!s) return null;"
            " return {multiple: s.multiple, index: el.index,"
            " selected: Array.from(s.options).filter(o => o.selected)"
            ".map(o => o.index)}; }")
        if info is None:
            self._act("click")
            return
        select = self._page.injected.call_raw(
            self._ctx, "(el) => el.closest('select')", [{"objectId": self._oid}])
        wanted = [info["index"]]
        if info["multiple"]:
            current = set(info["selected"])
            current ^= {info["index"]}
            wanted = sorted(current)
        try:
            self._page.actions.select_option(
                _HANDLE, [{"index": i} for i in wanted],
                frame_id=self._frame_id, element_id=select["objectId"],
                timeout=self._parent._action_timeout())
        except Exception as e:
            raise _bridge.translate(e) from None

    def submit(self) -> None:
        """Submits a form.

        ⛔ NOT BY SCRIPT. The form's submit control, when it has one, is
        clicked with the pointer; otherwise Enter is pressed in the element,
        which is how a person submits a form without a button. A submission
        started by `form.submit()` fires no submit event at all and one from
        `requestSubmit()` is not something a hand produces.
        """
        found = self._page.injected.call_raw(
            self._ctx,
            "(el) => { const f = el.form || el.closest('form');"
            " if (!f) return 'noform';"
            " return f.querySelector('button[type=submit], input[type=submit],"
            " button:not([type]), input[type=image]') || 'nobutton'; }",
            [{"objectId": self._oid}])
        if found.get("value") == "noform":
            raise exc.NoSuchElementException(
                "To submit an element, it must be nested inside a form element")
        if "objectId" in found:
            WebElement(self._parent, self._page, self._frame_id,
                       found["objectId"]).click()
            return
        self._act("press", "Enter")

    def clear(self) -> None:
        """Clears the text if it's a text entry element."""
        try:
            self._act("fill", "")
        except exc.JavascriptException as e:
            raise exc.InvalidElementStateException(str(e)) from None

    def send_keys(self, *value: str) -> None:
        """Simulates typing into the element.

        A file input receives the paths instead (one per line for several
        files), exactly as in Selenium. Anything else is focused and typed into
        with the session's rhythm; `Keys` modifiers stay down until they are
        sent again, until `Keys.NULL`, or until the end of the call.
        """
        text = "".join(str(v) for v in value)
        kind = self._call("(el) => ((el.localName || '') === 'input') ?"
                          " (el.type || '').toLowerCase() : null")
        if kind == "file":
            files = [os.path.abspath(p) for p in text.split("\n") if p]
            for path in files:
                if not os.path.exists(path):
                    raise exc.InvalidArgumentException("File not found: %s" % path)
            self._act("set_input_files", files)
            return
        self._act("focus")
        try:
            _bridge.type_keys(self._page.actions, text, sticky=True)
        except exc.WebDriverException:
            raise
        except Exception as e:
            raise _bridge.translate(e) from None

    # ── screenshots ─────────────────────────────────────────────────────────
    @property
    def screenshot_as_base64(self) -> str:
        """The element's screenshot as a base64 encoded PNG."""
        self._check_alive()
        try:
            self._page.injected.scroll_into_view(self._frame_id, self._oid)
        except Exception:
            pass
        r = self.rect
        return self._parent._screenshot_clip(
            self._page, {"x": r["x"], "y": r["y"],
                         "width": max(1, r["width"]),
                         "height": max(1, r["height"])})

    @property
    def screenshot_as_png(self) -> bytes:
        """The element's screenshot as PNG bytes."""
        return base64.b64decode(self.screenshot_as_base64.encode("ascii"))

    def screenshot(self, filename) -> bool:
        """Saves the element's screenshot to a PNG file."""
        if not str(filename).lower().endswith(".png"):
            import warnings
            warnings.warn("name used for saved screenshot does not match file "
                          "type. It should end with a `.png` extension",
                          UserWarning, stacklevel=2)
        png = self.screenshot_as_png
        try:
            with open(filename, "wb") as f:
                f.write(png)
        except OSError:
            return False
        return True

    # ── finding ─────────────────────────────────────────────────────────────
    def find_element(self, by=By.ID, value=None) -> WebElement:
        """Find the first element below this one."""
        return self._parent._find(self._page, self._frame_id, self, by, value,
                                  single=True)

    def find_elements(self, by=By.ID, value=None) -> List[WebElement]:
        """Find every element below this one."""
        return self._parent._find(self._page, self._frame_id, self, by, value,
                                  single=False)


__all__ = ["WebElement"]
