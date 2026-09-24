"""`ScrollOrigin`: where a wheel scroll starts, like Selenium's."""
from __future__ import annotations

from typing import Union


class ScrollOrigin:
    def __init__(self, origin, x_offset: int, y_offset: int) -> None:
        self._origin = origin
        self._x_offset = x_offset
        self._y_offset = y_offset

    @classmethod
    def from_element(cls, element, x_offset: int = 0, y_offset: int = 0):
        return cls(element, x_offset, y_offset)

    @classmethod
    def from_viewport(cls, x_offset: int = 0, y_offset: int = 0):
        return cls("viewport", x_offset, y_offset)

    @property
    def origin(self) -> Union[str, object]:
        return self._origin

    @property
    def x_offset(self) -> int:
        return self._x_offset

    @property
    def y_offset(self) -> int:
        return self._y_offset


__all__ = ["ScrollOrigin"]
