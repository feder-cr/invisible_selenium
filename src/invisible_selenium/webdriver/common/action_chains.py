"""`ActionChains`: queued pointer, keyboard and wheel actions, like Selenium's.

⛔ THE POINTER TRAVELS. Selenium's `move_to_element` is a W3C pointerMove,
which geckodriver delivers as a straight line with evenly spaced events over
`duration` ms. Here every move is drawn by the session's path generator and
delivered under the engine's pacing, the same movement invisible_playwright
makes; presses have the session's durations and keys its typing rhythm. The
queue, the methods and their arguments are Selenium's.
"""
from __future__ import annotations

import random
import time
from typing import Callable, List, Optional

from ... import _bridge
from ...common import exceptions as exc
from .actions.wheel_input import ScrollOrigin

#: Buttons as W3C numbers them; the engine's mask table is keyed the same way.
_LEFT, _MIDDLE, _RIGHT = 0, 1, 2


class ActionChains:
    def __init__(self, driver, duration: int = 250, devices=None) -> None:
        self._driver = driver
        #: Kept for signature parity. The duration of a move is the session's
        #: motion budget (`humanize=`), not a per-chain number: one hand does
        #: not move at two speeds depending on which API asked.
        self._duration = duration
        self._actions: List[Callable[[], None]] = []
        self._held_keys: List[str] = []
        self._held_button: Optional[int] = None

    # ── running ─────────────────────────────────────────────────────────────
    def perform(self) -> None:
        """Performs all stored actions, in order."""
        self._driver._check_alert()
        for action in self._actions:
            try:
                action()
            except exc.WebDriverException:
                raise
            except Exception as e:
                raise _bridge.translate(e) from None

    def reset_actions(self) -> None:
        """Clears the stored actions, and releases what is still held."""
        self._actions.clear()
        actions = self._engine()
        for name in reversed(self._held_keys):
            try:
                actions.keyboard.up(name)
            except Exception:
                pass
        self._held_keys.clear()
        if self._held_button is not None:
            try:
                actions.mouse_up(button=self._held_button)
            except Exception:
                pass
            self._held_button = None

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        pass

    def _add(self, fn: Callable[[], None]):
        self._actions.append(fn)
        return self

    def _engine(self):
        return self._driver._current_page().actions

    # ── geometry ────────────────────────────────────────────────────────────
    def _center(self, element, dx: float = 0, dy: float = 0):
        """The element's centre in viewport pixels, scrolled into view first.

        ⛔ W3C refuses a move to an element outside the viewport; a person
        scrolls to it first, and so does this, with the native scroll of the
        utility world."""
        element._check_alive()
        page = element._page
        page.injected.scroll_into_view(element._frame_id, element._oid)
        point = page.actions._center_point(element._frame_id, element._oid)
        if point is None:
            raise exc.MoveTargetOutOfBoundsException(
                "the element has no box to move to")
        return point[0] + dx, point[1] + dy

    def _move_to(self, x: float, y: float) -> None:
        actions = self._engine()
        w, h = actions._viewport()
        if w is not None and h is not None and not (0 <= x <= w and 0 <= y <= h):
            raise exc.MoveTargetOutOfBoundsException(
                "(%s, %s) is out of bounds of viewport width (%s) and height "
                "(%s)" % (x, y, w, h))
        buttons = 0
        if self._held_button is not None:
            from ..._juggler.keyboard import BUTTON_MASK
            buttons = BUTTON_MASK[self._held_button]
        actions.glide_to(x, y, buttons=buttons)

    def _press(self, button: int, clicks: int = 1) -> None:
        actions = self._engine()
        actions._click_at_point(actions.position, button=button, clicks=clicks)

    # ── pointer ─────────────────────────────────────────────────────────────
    def click(self, on_element=None):
        """Clicks an element, or where the pointer is."""
        def run():
            if on_element is not None:
                self._move_to(*self._center(on_element))
            self._press(_LEFT)
        return self._add(run)

    def click_and_hold(self, on_element=None):
        """Holds down the left mouse button on an element or where it is."""
        def run():
            if on_element is not None:
                self._move_to(*self._center(on_element))
            self._engine().mouse_down(button=_LEFT)
            self._held_button = _LEFT
        return self._add(run)

    def context_click(self, on_element=None):
        """Right-clicks an element or where the pointer is."""
        def run():
            if on_element is not None:
                self._move_to(*self._center(on_element))
            self._press(_RIGHT)
        return self._add(run)

    def double_click(self, on_element=None):
        """Double-clicks an element or where the pointer is."""
        def run():
            if on_element is not None:
                self._move_to(*self._center(on_element))
            self._press(_LEFT, clicks=2)
        return self._add(run)

    def release(self, on_element=None):
        """Releases a held mouse button on an element or where it is."""
        def run():
            if on_element is not None:
                self._move_to(*self._center(on_element))
            self._engine().mouse_up(button=self._held_button or _LEFT)
            self._held_button = None
        return self._add(run)

    def drag_and_drop(self, source, target):
        """Holds the button on the source, travels to the target, releases."""
        self.click_and_hold(source)
        self.release(target)
        return self

    def drag_and_drop_by_offset(self, source, xoffset: int, yoffset: int):
        """Holds the button on the source, travels by an offset, releases."""
        self.click_and_hold(source)
        self.move_by_offset(xoffset, yoffset)
        self.release()
        return self

    def move_by_offset(self, xoffset: int, yoffset: int):
        """Moves the pointer by an offset from where it is."""
        def run():
            x, y = self._engine().position
            self._move_to(x + xoffset, y + yoffset)
        return self._add(run)

    def move_to_element(self, to_element):
        """Moves the pointer to the middle of an element."""
        return self._add(lambda: self._move_to(*self._center(to_element)))

    def move_to_element_with_offset(self, to_element, xoffset: int, yoffset: int):
        """Moves the pointer to an offset from the middle of an element, which
        is Selenium 4's origin for this offset."""
        return self._add(lambda: self._move_to(
            *self._center(to_element, xoffset, yoffset)))

    # ── keyboard ────────────────────────────────────────────────────────────
    def _focus(self, element) -> None:
        # Selenium clicks the element first; so does this, with the pointer.
        element.click()

    def key_down(self, value: str, element=None):
        """Presses a key without releasing it (for modifiers)."""
        def run():
            if element is not None:
                self._focus(element)
            name = _bridge.key_name(value) if _bridge.is_special(value) else value
            self._engine().keyboard.down(name)
            self._held_keys.append(name)
        return self._add(run)

    def key_up(self, value: str, element=None):
        """Releases a key pressed with key_down."""
        def run():
            if element is not None:
                self._focus(element)
            name = _bridge.key_name(value) if _bridge.is_special(value) else value
            self._engine().keyboard.up(name)
            if name in self._held_keys:
                self._held_keys.remove(name)
        return self._add(run)

    def send_keys(self, *keys_to_send: str):
        """Sends keys to the element that has focus; each key is pressed and
        released on its own, as in Selenium's ActionChains."""
        text = "".join(str(k) for k in keys_to_send)
        return self._add(lambda: _bridge.type_keys(self._engine(), text,
                                                   sticky=False))

    def send_keys_to_element(self, element, *keys_to_send: str):
        """Clicks an element, then sends keys to it."""
        text = "".join(str(k) for k in keys_to_send)

        def run():
            self._focus(element)
            _bridge.type_keys(self._engine(), text, sticky=False)
        return self._add(run)

    # ── time and wheel ──────────────────────────────────────────────────────
    def pause(self, seconds: float | int):
        """Pauses all inputs for the given duration in seconds."""
        return self._add(lambda: time.sleep(max(0.0, float(seconds))))

    def _wheel(self, dx: float, dy: float) -> None:
        """A scroll as notches, not one jump.

        ⛔ A WHEEL MOVES IN STEPS. One event carrying a thousand pixels is not
        something a wheel produces; the delta is split into notches of about a
        hundred pixels with a short, varying gap between them, from a stream
        seeded by the session so a replayed seed scrolls the same way."""
        actions = self._engine()
        seed = getattr(actions, "session_seed", None)
        rng = random.Random(seed if seed is not None else 0)
        steps = max(1, int(max(abs(dx), abs(dy)) // 100) + 1)
        for i in range(steps):
            actions.wheel(dx / steps, dy / steps)
            if i < steps - 1:
                time.sleep(rng.uniform(0.018, 0.045))

    def scroll_to_element(self, element):
        """Scrolls with the wheel until the element is in view."""
        def run():
            element._check_alive()
            page = element._page
            box = page.injected.bounding_box(element._frame_id, element._oid)
            w, h = page.actions._viewport()
            if box is None or w is None:
                return
            dy = 0.0
            if box["y"] < 0 or box["y"] + box["height"] > h:
                dy = box["y"] + box["height"] / 2.0 - h / 2.0
            dx = 0.0
            if box["x"] < 0 or box["x"] + box["width"] > w:
                dx = box["x"] + box["width"] / 2.0 - w / 2.0
            if dx or dy:
                self._wheel(dx, dy)
        return self._add(run)

    def scroll_by_amount(self, delta_x: int, delta_y: int):
        """Scrolls by the given amounts, from where the pointer is."""
        return self._add(lambda: self._wheel(delta_x, delta_y))

    def scroll_from_origin(self, scroll_origin: ScrollOrigin, delta_x: int,
                           delta_y: int):
        """Moves the pointer to an origin, then scrolls by the given amounts."""
        if not isinstance(scroll_origin, ScrollOrigin):
            raise TypeError("Expected object of type ScrollOrigin, got: "
                            "%s" % type(scroll_origin))

        def run():
            if scroll_origin.origin == "viewport":
                self._move_to(scroll_origin.x_offset, scroll_origin.y_offset)
            else:
                self._move_to(*self._center(scroll_origin.origin,
                                            scroll_origin.x_offset,
                                            scroll_origin.y_offset))
            self._wheel(delta_x, delta_y)
        return self._add(run)


__all__ = ["ActionChains"]
