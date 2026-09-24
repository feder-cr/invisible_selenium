"""The exceptions Selenium raises, with the same names and the same hierarchy.

A script that catches `NoSuchElementException` or `TimeoutException` from
`selenium.common.exceptions` catches the same thing from here after changing
the import, and `except WebDriverException` still catches all of them.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

SUPPORT_MSG = "For documentation on this error, please visit:"
ERROR_URL = "https://www.selenium.dev/documentation/webdriver/troubleshooting/errors"


class WebDriverException(Exception):
    """Base webdriver exception."""

    def __init__(self, msg: Any | None = None, screen: str | None = None,
                 stacktrace: Sequence[str] | None = None) -> None:
        super().__init__()
        self.msg = msg
        self.screen = screen
        self.stacktrace = stacktrace

    def __str__(self) -> str:
        text = f"Message: {self.msg}\n"
        if self.screen:
            text += "Screenshot: available via screen\n"
        if self.stacktrace:
            text += "Stacktrace:\n" + "\n".join(self.stacktrace)
        return text


class _WithSupport(WebDriverException):
    """An exception whose message carries Selenium's troubleshooting link."""

    _anchor = ""

    def __init__(self, msg: Any | None = None, screen: str | None = None,
                 stacktrace: Sequence[str] | None = None) -> None:
        super().__init__(f"{msg}; {SUPPORT_MSG} {ERROR_URL}#{self._anchor}",
                         screen, stacktrace)


class InvalidSwitchToTargetException(WebDriverException):
    """Thrown when frame or window target to be switched doesn't exist."""


class NoSuchFrameException(InvalidSwitchToTargetException):
    """Thrown when frame target to be switched doesn't exist."""


class NoSuchWindowException(InvalidSwitchToTargetException):
    """Thrown when window target to be switched doesn't exist."""


class NoSuchElementException(_WithSupport):
    """Thrown when element could not be found."""
    _anchor = "nosuchelementexception"


class NoSuchAttributeException(WebDriverException):
    """Thrown when the attribute of element could not be found."""


class NoSuchShadowRootException(WebDriverException):
    """Thrown when trying to access the shadow root of an element when it does
    not have a shadow root attached."""


class StaleElementReferenceException(_WithSupport):
    """Thrown when a reference to an element is now "stale"."""
    _anchor = "staleelementreferenceexception"


class InvalidElementStateException(WebDriverException):
    """Thrown when a command could not be completed because the element is in
    an invalid state."""


class UnexpectedAlertPresentException(WebDriverException):
    """Thrown when an unexpected alert has appeared."""

    def __init__(self, msg: Any | None = None, screen: str | None = None,
                 stacktrace: Sequence[str] | None = None,
                 alert_text: str | None = None) -> None:
        super().__init__(msg, screen, stacktrace)
        self.alert_text = alert_text

    def __str__(self) -> str:
        return f"Alert Text: {self.alert_text}\n{super().__str__()}"


class NoAlertPresentException(WebDriverException):
    """Thrown when switching to no presented alert."""


class ElementNotVisibleException(InvalidElementStateException):
    """Thrown when an element is present on the DOM, but it is not visible."""

    def __init__(self, msg: Any | None = None, screen: str | None = None,
                 stacktrace: Sequence[str] | None = None) -> None:
        super().__init__(f"{msg}; {SUPPORT_MSG} {ERROR_URL}#elementnotvisibleexception",
                         screen, stacktrace)


class ElementNotInteractableException(InvalidElementStateException):
    """Thrown when an element is present in the DOM but interactions with it
    would hit another element due to paint order."""

    def __init__(self, msg: Any | None = None, screen: str | None = None,
                 stacktrace: Sequence[str] | None = None) -> None:
        super().__init__(f"{msg}; {SUPPORT_MSG} {ERROR_URL}#elementnotinteractableexception",
                         screen, stacktrace)


class ElementNotSelectableException(InvalidElementStateException):
    """Thrown when trying to select an unselectable element."""


class InvalidCookieDomainException(WebDriverException):
    """Thrown when attempting to add a cookie under a different domain."""


class UnableToSetCookieException(WebDriverException):
    """Thrown when a driver fails to set a cookie."""


class TimeoutException(WebDriverException):
    """Thrown when a command does not complete in enough time."""


class MoveTargetOutOfBoundsException(WebDriverException):
    """Thrown when the target provided to the `ActionsChains` move() method is
    invalid, i.e. out of document."""


class UnexpectedTagNameException(WebDriverException):
    """Thrown when a support class did not get an expected web element."""


class InvalidSelectorException(_WithSupport):
    """Thrown when the selector used to find an element is not valid."""
    _anchor = "invalidselectorexception"


class ImeNotAvailableException(WebDriverException):
    """Thrown when IME support is not available."""


class ImeActivationFailedException(WebDriverException):
    """Thrown when activating an IME engine has failed."""


class InvalidArgumentException(WebDriverException):
    """The arguments passed to a command are either invalid or malformed."""


class JavascriptException(WebDriverException):
    """An error occurred while executing JavaScript supplied by the user."""


class NoSuchCookieException(WebDriverException):
    """No cookie matching the given path name was found."""


class ScreenshotException(WebDriverException):
    """A screen capture was made impossible."""


class ElementClickInterceptedException(_WithSupport):
    """The Element Click command could not be completed because the element
    receiving the events is obscuring the element that was requested to be
    clicked."""
    _anchor = "elementclickinterceptedexception"


class InsecureCertificateException(WebDriverException):
    """Navigation caused the user agent to hit a certificate warning."""


class InvalidCoordinatesException(WebDriverException):
    """The coordinates provided to an interaction's operation are invalid."""


class InvalidSessionIdException(_WithSupport):
    """Occurs if the given session id is not in the list of active sessions."""
    _anchor = "invalidsessionidexception"


class SessionNotCreatedException(_WithSupport):
    """A new session could not be created."""
    _anchor = "sessionnotcreatedexception"


class UnknownMethodException(WebDriverException):
    """The requested command matched a known URL but did not match any methods
    for that URL."""


class NoSuchDriverException(_WithSupport):
    """Raised when driver is not specified and cannot be located."""
    _anchor = "driver_location"


class DetachedShadowRootException(WebDriverException):
    """Raised when referenced shadow root is no longer attached to the DOM."""
