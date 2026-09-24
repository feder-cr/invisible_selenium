"""`Options`: Selenium's FirefoxOptions, reduced to what reaches this browser.

The arguments, the preferences and the binary location have a place in the
launch (see `webdriver.Firefox`). Everything else Selenium's Options carries
exists for geckodriver or for a Firefox that is not this one.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Options:
    KEY = "moz:firefoxOptions"

    def __init__(self) -> None:
        self._arguments: List[str] = []
        self._preferences: Dict[str, Any] = {}
        self._binary_location: str = ""
        self.page_load_strategy = "normal"
        self.accept_insecure_certs = False

    # ── arguments ───────────────────────────────────────────────────────────
    @property
    def arguments(self) -> List[str]:
        return self._arguments

    def add_argument(self, argument: str) -> None:
        if not argument:
            raise ValueError("argument can not be null")
        self._arguments.append(argument)

    # ── preferences ─────────────────────────────────────────────────────────
    @property
    def preferences(self) -> Dict[str, Any]:
        return self._preferences

    def set_preference(self, name: str, value: Any) -> None:
        """A Firefox pref, layered on top of the profile's.

        ⛔ A pref the fingerprint depends on can be overridden this way, and
        the result is a session that contradicts its own profile. That is the
        caller's call to make, as it is with ``extra_prefs=``."""
        self._preferences[name] = value

    # ── the binary ──────────────────────────────────────────────────────────
    @property
    def binary_location(self) -> str:
        return self._binary_location

    @binary_location.setter
    def binary_location(self, value: str) -> None:
        self._binary_location = value

    # ── headless, as Selenium spells it ─────────────────────────────────────
    @property
    def headless(self) -> bool:
        return "-headless" in self._arguments or "--headless" in self._arguments

    def to_capabilities(self) -> dict:
        caps: Dict[str, Any] = {"browserName": "firefox",
                                "pageLoadStrategy": self.page_load_strategy,
                                "acceptInsecureCerts": self.accept_insecure_certs}
        opts: Dict[str, Any] = {}
        if self._arguments:
            opts["args"] = list(self._arguments)
        if self._preferences:
            opts["prefs"] = dict(self._preferences)
        if self._binary_location:
            opts["binary"] = self._binary_location
        if opts:
            caps[self.KEY] = opts
        return caps


__all__ = ["Options"]
