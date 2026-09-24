"""`WebDriverWait`: poll a condition until it holds, like Selenium's."""
from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Optional

from ...common.exceptions import NoSuchElementException, TimeoutException

POLL_FREQUENCY: float = 0.5
IGNORED_EXCEPTIONS: tuple = (NoSuchElementException,)


class WebDriverWait:
    def __init__(self, driver, timeout: float,
                 poll_frequency: float = POLL_FREQUENCY,
                 ignored_exceptions: Optional[Iterable[type]] = None) -> None:
        self._driver = driver
        self._timeout = float(timeout)
        self._poll = poll_frequency or POLL_FREQUENCY
        exceptions = list(IGNORED_EXCEPTIONS)
        if ignored_exceptions:
            try:
                exceptions.extend(iter(ignored_exceptions))
            except TypeError:
                exceptions.append(ignored_exceptions)
        self._ignored_exceptions = tuple(exceptions)

    def __repr__(self) -> str:
        return '<%s.%s (session="%s")>' % (type(self).__module__,
                                          type(self).__name__,
                                          getattr(self._driver, "session_id", None))

    def until(self, method: Callable[[Any], Any], message: str = ""):
        """Calls `method` until it returns something truthy, and returns it."""
        screen = None
        stacktrace = None
        end_time = time.monotonic() + self._timeout
        while True:
            try:
                value = method(self._driver)
                if value:
                    return value
            except self._ignored_exceptions as e:
                screen = getattr(e, "screen", None)
                stacktrace = getattr(e, "stacktrace", None)
            if time.monotonic() > end_time:
                break
            time.sleep(self._poll)
        raise TimeoutException(message, screen, stacktrace)

    def until_not(self, method: Callable[[Any], Any], message: str = ""):
        """Calls `method` until it returns something falsy (or raises one of
        the ignored exceptions, which counts as True)."""
        end_time = time.monotonic() + self._timeout
        while True:
            try:
                value = method(self._driver)
                if not value:
                    return value
            except self._ignored_exceptions:
                return True
            if time.monotonic() > end_time:
                break
            time.sleep(self._poll)
        raise TimeoutException(message)


__all__ = ["WebDriverWait", "POLL_FREQUENCY", "IGNORED_EXCEPTIONS"]
