"""Timeouts, history and documents that go mid-command, as in Selenium and
Marionette, on a real engine.

What 0.3.7 did instead, each one measured below:

- a 0 timeout was read as "the default": `set_page_load_timeout(0)` waited
  300 s, `set_script_timeout(0)` 30 s, where Marionette times out at once;
- `driver.timeouts = Timeouts(implicit_wait=3)` set the other two to 0,
  where Selenium sends only the fields that are not 0 and the rest stay;
- `driver.timeouts` handed back the session's own object, so changing a
  value on it changed the session, which Selenium's never does;
- the implicit wait looked every 100 ms, Marionette every 10;
- `back()` to a same-document entry waited half a second of grace, where
  `hashchange` and `popstate` end Marionette's wait at once;
- `ActionChains.key_down(key, element)` clicked through `WebElement.click`,
  whose checks refuse a covered element, where Selenium's pointer click has
  none;
- a click whose press navigates raised about the document that went
  ("mouseup landed on ...": the engine loop's landing verdict judged the
  release on the next document), where Marionette answers null
  (`NO_RETRY_METHODS`). The click that tries once has no verdict to give.

A key that navigates did not raise in 0.3.7 either: that test is a guard.
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium import _bridge
from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.action_chains import ActionChains
from invisible_selenium.webdriver.common.by import By
from invisible_selenium.webdriver.common.keys import Keys
from invisible_selenium.webdriver.common.timeouts import Timeouts

pytestmark = pytest.mark.e2e

PAGE = b"""<!doctype html><html><head><title>start</title></head>
<body style="margin:0">
<div style="position:relative;width:200px;height:40px">
  <button id=covered>covered</button>
  <div id=overlay style="position:absolute;left:0;top:0;width:200px;height:40px"
       onclick="window.overlayClicks = (window.overlayClicks || 0) + 1"></div>
</div>
<button id=leave onmousedown="location.href = '/other'">leave on press</button>
<input id=typed onkeydown="location.href = '/other'">
<a id=hash href="#a">hash</a>
</body></html>"""
OTHER = b"<!doctype html><html><head><title>other</title></head><body>other</body></html>"
SLOW = b"<!doctype html><html><head><title>slow</title></head><body>slow</body></html>"


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/slow"):
                time.sleep(1.5)
                body = SLOW
            elif self.path.startswith("/other"):
                body = OTHER
            else:
                body = PAGE
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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


@pytest.fixture(scope="module")
def driver(firefox_binary):
    from invisible_selenium import webdriver
    d = webdriver.Firefox(seed=4246, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


@pytest.fixture
def page(driver, site):
    driver.set_page_load_timeout(300)
    driver.set_script_timeout(30)
    driver.implicitly_wait(0)
    driver.get(site)
    yield driver
    driver.set_page_load_timeout(300)
    driver.set_script_timeout(30)
    driver.implicitly_wait(0)


# ── timeouts ────────────────────────────────────────────────────────────────
def test_a_page_load_timeout_of_zero_times_out_at_once(page, site):
    page.set_page_load_timeout(0)
    began = time.monotonic()
    with pytest.raises(exc.TimeoutException, match=r"Navigation timed out after 0 ms"):
        page.get(site + "slow")
    assert time.monotonic() - began < 1.0


def test_a_script_timeout_of_zero_times_out_an_asynchronous_script(page):
    page.set_script_timeout(0)
    # A synchronous result wins Marionette's race with its zero timer.
    assert page.execute_script("return 1") == 1
    with pytest.raises(exc.TimeoutException, match=r"Timed out after 0 ms"):
        page.execute_async_script("setTimeout(() => arguments[0](1), 1500)")


def test_setting_timeouts_keeps_the_fields_left_at_zero(page):
    page.set_page_load_timeout(7)
    page.timeouts = Timeouts(implicit_wait=3)
    t = page.timeouts
    assert (t.implicit_wait, t.page_load, t.script) == (3, 7, 30)


def test_the_timeouts_read_back_are_a_copy(page):
    t = page.timeouts
    t.implicit_wait = 9
    assert page.timeouts.implicit_wait == 0


def test_a_timeout_that_is_not_a_number_is_a_type_error(page):
    with pytest.raises(TypeError, match=r"Timeouts can only be an int or a float"):
        Timeouts(script=None)
    with pytest.raises(TypeError):
        page.set_script_timeout(None)


def test_the_implicit_wait_looks_every_ten_milliseconds(page, monkeypatch):
    steps = []
    poll = _bridge.poll

    def recording(deadline, interval=0.1):
        steps.append(interval)
        return poll(deadline, interval)
    monkeypatch.setattr(_bridge, "poll", recording)
    page.implicitly_wait(0.2)
    with pytest.raises(exc.NoSuchElementException):
        page.find_element(By.ID, "nowhere")
    assert steps and set(steps) == {0.01}


# ── history ─────────────────────────────────────────────────────────────────
def test_back_and_forward_on_a_hash_end_at_once(page, site):
    page.find_element(By.ID, "hash").click()
    assert page.current_url == site + "#a"
    took = []
    for _ in range(3):
        began = time.monotonic()
        page.back()
        took.append(time.monotonic() - began)
        assert page.current_url == site
        began = time.monotonic()
        page.forward()
        took.append(time.monotonic() - began)
        assert page.current_url == site + "#a"
    # The grace this replaced was half a second on every one of them.
    assert min(took) < 0.35, took


def test_back_to_another_document_reads_it_at_once(page, site):
    page.get(site + "other")
    page.back()
    assert page.title == "start"
    assert page.find_element(By.ID, "covered").text == "covered"


# ── actions with an element ─────────────────────────────────────────────────
def test_key_down_on_an_element_clicks_it_with_the_pointer_and_no_check(page):
    """Selenium's `key_down(key, element)` is `self.click(element)` first: the
    press lands on whatever is there, the overlay here, and nothing is
    refused."""
    covered = page.find_element(By.ID, "covered")
    ActionChains(page).key_down(Keys.SHIFT, covered).key_up(Keys.SHIFT).perform()
    assert page.execute_script("return window.overlayClicks") == 1


# ── documents that go mid-command ───────────────────────────────────────────
def test_a_click_whose_press_navigates_is_not_an_error(page, site):
    for _ in range(3):
        page.get(site)
        page.find_element(By.ID, "leave").click()
        assert page.title == "other"


def test_send_keys_whose_key_navigates_is_not_an_error(page, site):
    for _ in range(3):
        page.get(site)
        page.find_element(By.ID, "typed").send_keys("abc")
        # The key took the page away; the next read is on the new one or on
        # its way to it, never an error about the old one.
        deadline = time.monotonic() + 10
        while page.title != "other" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert page.title == "other"
