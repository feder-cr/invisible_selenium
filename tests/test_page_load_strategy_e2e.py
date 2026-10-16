"""The page load strategy decides when a navigation command returns.

Until 0.3.6 `Options.page_load_strategy` was ignored: `get`, `back`,
`forward` and `refresh` waited for `load` whatever it said, a click waited for
nothing, and the capabilities reported "normal". Selenium's three, as
Marionette reads them (`navigate.sys.mjs`): "normal" returns at `load`,
"eager" at `DOMContentLoaded`, "none" once the navigation has started.
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.webdriver import FirefoxOptions
from invisible_selenium.webdriver.common.by import By

#: How long the slow document makes the browser wait for its first byte.
SLOW_DOCUMENT_S = 6.0
#: How long the late image holds `load` back after `DOMContentLoaded`.
LATE_IMAGE_S = 4.0

INDEX = b"""<!doctype html><html><head><title>index</title></head><body>
<a id=slow href="/slow">to the slow page</a>
</body></html>"""
WITH_IMAGE = (b"<!doctype html><html><head><title>with image</title></head>"
              b"<body>parsed<img src=/late.gif></body></html>")
SLOW = b"<!doctype html><html><head><title>slow page</title></head><body>arrived</body></html>"
GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ctype = "text/html; charset=utf-8"
            if self.path.startswith("/late.gif"):
                time.sleep(LATE_IMAGE_S)
                body, ctype = GIF, "image/gif"
            elif self.path.startswith("/slow"):
                time.sleep(SLOW_DOCUMENT_S)
                body = SLOW
            elif self.path.startswith("/with-image"):
                body = WITH_IMAGE
            else:
                body = INDEX
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            # The image is fetched again on a refresh, so `load` is late again.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % srv.server_address[1]
    srv.shutdown()


def _driver(firefox_binary, strategy):
    from invisible_selenium import webdriver
    options = FirefoxOptions()
    options.page_load_strategy = strategy
    return webdriver.Firefox(options=options, seed=4245, binary_path=firefox_binary,
                             headless=True)


@pytest.fixture(scope="module")
def eager(firefox_binary):
    d = _driver(firefox_binary, "eager")
    yield d
    d.quit()


@pytest.fixture(scope="module")
def none(firefox_binary):
    d = _driver(firefox_binary, "none")
    yield d
    d.quit()


def _wait_for(driver, script, expected, limit=20):
    deadline = time.monotonic() + limit
    while True:
        got = driver.execute_script(script)
        if got == expected or time.monotonic() > deadline:
            return got
        time.sleep(0.05)


def test_an_unknown_strategy_is_refused_as_it_is_assigned():
    options = FirefoxOptions()
    with pytest.raises(ValueError,
                       match="Strategy can only be one of the following: normal, eager, none"):
        options.page_load_strategy = "fast"
    assert options.page_load_strategy == "normal"


@pytest.mark.e2e
def test_the_capabilities_say_the_strategy(eager, none):
    assert eager.capabilities["pageLoadStrategy"] == "eager"
    assert none.capabilities["pageLoadStrategy"] == "none"


@pytest.mark.e2e
def test_eager_get_returns_at_domcontentloaded(eager, site):
    eager.get(site + "with-image")
    # The image is still on its way: `load` has not fired.
    assert eager.execute_script("return document.readyState") == "interactive"
    assert eager.find_element(By.TAG_NAME, "body").text == "parsed"
    assert _wait_for(eager, "return document.readyState", "complete") == "complete"


@pytest.mark.e2e
def test_eager_refresh_returns_at_domcontentloaded(eager, site):
    eager.get(site + "with-image")
    assert _wait_for(eager, "return document.readyState", "complete") == "complete"
    eager.refresh()
    assert eager.execute_script("return document.readyState") == "interactive"


@pytest.mark.wall_clock
@pytest.mark.e2e
def test_none_get_returns_once_the_navigation_has_started(none, site):
    none.get(site)
    assert _wait_for(none, "return document.title", "index") == "index"
    began = time.monotonic()
    none.get(site + "slow")
    took = time.monotonic() - began
    assert took < SLOW_DOCUMENT_S - 1, took
    assert _wait_for(none, "return document.title", "slow page") == "slow page"


@pytest.mark.wall_clock
@pytest.mark.e2e
def test_none_refresh_returns_once_the_reload_has_started(none, site):
    none.get(site + "slow")
    assert _wait_for(none, "return document.title", "slow page") == "slow page"
    began = time.monotonic()
    none.refresh()
    took = time.monotonic() - began
    assert took < SLOW_DOCUMENT_S - 1, took


@pytest.mark.wall_clock
@pytest.mark.e2e
def test_none_click_does_not_wait_for_the_page_it_unloads_into(none, site):
    none.get(site)
    assert _wait_for(none, "return document.title", "index") == "index"
    link = none.find_element(By.ID, "slow")
    began = time.monotonic()
    link.click()
    took = time.monotonic() - began
    # The click itself takes a human hand's time; no page-load wait is added.
    assert took < SLOW_DOCUMENT_S - 1, took
    assert _wait_for(none, "return document.title", "slow page") == "slow page"
