"""`SwitchTo`: moving the driver between windows, frames and dialogs."""
from __future__ import annotations

from typing import Optional, Union

from ...common import exceptions as exc
from ..common.alert import Alert
from ..common.by import By
from ..common.window import WindowTypes
from .webelement import WebElement


class SwitchTo:
    def __init__(self, driver) -> None:
        self._driver = driver

    @property
    def active_element(self) -> WebElement:
        """The element with focus, or the body when nothing has it."""
        return self._driver._active_element()

    @property
    def alert(self) -> Alert:
        """The open dialog of the current window."""
        return Alert(self._driver)

    def default_content(self) -> None:
        """Switch focus to the top-level document."""
        self._driver._switch_frame(None)

    def frame(self, frame_reference: Union[str, int, WebElement]) -> None:
        """Switch focus to a frame, by index, name or id, or element."""
        driver = self._driver
        if isinstance(frame_reference, str):
            try:
                element = driver.find_element(By.ID, frame_reference)
            except exc.NoSuchElementException:
                try:
                    element = driver.find_element(By.NAME, frame_reference)
                except exc.NoSuchElementException:
                    raise exc.NoSuchFrameException(frame_reference) from None
            frame_reference = element
        if isinstance(frame_reference, int):
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            if frame_reference < 0 or frame_reference >= len(frames):
                raise exc.NoSuchFrameException(str(frame_reference))
            frame_reference = frames[frame_reference]
        if not isinstance(frame_reference, WebElement):
            raise exc.InvalidArgumentException(
                "frame reference must be an index, a name or id, or an element")
        driver._enter_frame(frame_reference)

    def new_window(self, type_hint: Optional[str] = None) -> None:
        """Open a new tab or window and switch to it."""
        if type_hint not in (None, WindowTypes.TAB, WindowTypes.WINDOW):
            raise exc.InvalidArgumentException(
                "type_hint must be 'tab' or 'window'")
        self._driver._new_window()

    def parent_frame(self) -> None:
        """Switch focus to the parent of the current frame."""
        self._driver._parent_frame()

    def window(self, window_name: str) -> None:
        """Switch focus to the window with this handle."""
        self._driver._switch_window(window_name)


__all__ = ["SwitchTo"]
