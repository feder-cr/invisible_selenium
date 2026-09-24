"""invisible_selenium - Selenium's API for a patched Firefox with a stealth profile.

Quickstart:

    from invisible_selenium import webdriver
    from invisible_selenium.webdriver.common.by import By

    driver = webdriver.Firefox(seed=42)        # same seed, same fingerprint
    driver.get("https://example.com")
    driver.find_element(By.TAG_NAME, "a").click()   # the pointer travels there
    driver.quit()

A replica of invisible_playwright with Selenium's contract: the same engine,
the same binary, the same profile and the same human-paced input, driven over
Juggler - with no geckodriver and no Marionette.
"""
# ── Import-time core assertion, and repair ───────────────────────────────────
# Runs BEFORE every other import, exactly as in invisible_playwright: is the
# installed invisible-core the version this distribution declares? A mismatch
# is repaired in place when nothing has imported the core yet. See `_pin.py`.
from ._pin import enforce_core_pin as _enforce_core_pin
_enforce_core_pin()

from invisible_core import BINARY_VERSION, FIREFOX_UPSTREAM_VERSION
from invisible_core import ensure_binary

from . import webdriver
from ._version import __install_record_version__, __version__

__all__ = [
    "webdriver",
    "ensure_binary",
    "BINARY_VERSION",
    "FIREFOX_UPSTREAM_VERSION",
    "__version__",
    "__install_record_version__",
]
