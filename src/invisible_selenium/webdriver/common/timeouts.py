"""`Timeouts`: the three session timeouts, like Selenium's.

⛔ THE SAME OBJECT AS SELENIUM'S, NOT A LOOK-ALIKE. Values are kept in whole
milliseconds and read back in seconds; anything but an int or a float is a
`TypeError` ("Timeouts can only be an int or a float"), None included; and
`_to_json` names only the fields that are not 0, which is what makes
`driver.timeouts = Timeouts(implicit_wait=10)` change the implicit wait and
leave the other two as they were. Until 0.3.7 the setter replaced all three,
so that line set the page load timeout to 0, which this package then read as
"the default".
"""
from __future__ import annotations


class _TimeoutsDescriptor:
    """One of the three values: seconds out, whole milliseconds in.

    Setting it does not change the session, as in Selenium: a `Timeouts` is
    sent with `driver.timeouts = ...`."""

    def __init__(self, name):
        self.name = name

    def __get__(self, obj, cls) -> float:
        return getattr(obj, self.name) / 1000

    def __set__(self, obj, value) -> None:
        setattr(obj, self.name, obj._convert(value))


class Timeouts:
    def __init__(self, implicit_wait: float = 0, page_load: float = 0,
                 script: float = 0) -> None:
        self._implicit_wait = self._convert(implicit_wait)
        self._page_load = self._convert(page_load)
        self._script = self._convert(script)

    implicit_wait = _TimeoutsDescriptor("_implicit_wait")
    page_load = _TimeoutsDescriptor("_page_load")
    script = _TimeoutsDescriptor("_script")

    def _convert(self, timeout: float) -> int:
        if isinstance(timeout, (int, float)):
            return int(float(timeout) * 1000)
        raise TypeError("Timeouts can only be an int or a float")

    def _to_json(self) -> dict:
        timeouts = {}
        if self._implicit_wait:
            timeouts["implicit"] = self._implicit_wait
        if self._page_load:
            timeouts["pageLoad"] = self._page_load
        if self._script:
            timeouts["script"] = self._script
        return timeouts


__all__ = ["Timeouts"]
