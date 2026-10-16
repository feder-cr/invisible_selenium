"""`send_keys` and `click` do what geckodriver does, on a real engine.

Two defects of 0.3.5, both found by reading Marionette (Firefox's own
WebDriver server, which geckodriver drives) side by side with this package:

- `send_keys` focused through the engine's `focus`, which is Playwright's and
  puts the caret at the START of a field it focuses: a pre-filled field got the
  text in FRONT of its value. Marionette focuses only an element that does not
  have the focus, and moves the caret to the end (`moveCaretToEnd`). And an
  element that cannot take the focus had the keys typed wherever the focus
  was, where Marionette raises "is not reachable by keyboard".
- `click` returned at once. Marionette waits for the page a click unloads
  into (`clickElement`, `waitForNavigationCompleted`), so the next line of a
  test reads the new page; here it read the old one.
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.by import By

pytestmark = pytest.mark.e2e

FORM = b"""<!doctype html><html><head><title>form</title></head><body>
<input id=filled value="abc">
<textarea id=area>line</textarea>
<input id=placed value="abcd">
<div id=plain>not focusable</div>
<a id=slow href="/slow">to the slow page</a>
<button id=noop onclick="window.clicked = (window.clicked || 0) + 1">noop</button>
<a id=hash href="#here">hash</a>
</body></html>"""
SLOW = b"<!doctype html><html><head><title>slow page</title></head><body>arrived<img src=/slowimg></body></html>"
#: A 1x1 GIF, served late, so the page's `load` comes well after its commit.
GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ctype = "text/html; charset=utf-8"
            if self.path.startswith("/slowimg"):
                time.sleep(1.5)
                body, ctype = GIF, "image/gif"
            elif self.path.startswith("/slow"):
                time.sleep(1.0)
                body = SLOW
            else:
                body = FORM
            self.send_response(200)
            self.send_header("Content-Type", ctype)
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
    d = webdriver.Firefox(seed=4244, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


def test_send_keys_appends_to_a_filled_input(driver, site):
    driver.get(site)
    field = driver.find_element(By.ID, "filled")
    field.send_keys("XYZ")
    assert field.get_attribute("value") == "abcXYZ"


def test_send_keys_appends_to_a_filled_textarea(driver, site):
    driver.get(site)
    area = driver.find_element(By.ID, "area")
    area.send_keys(" more")
    assert area.get_property("value") == "line more"


def test_send_keys_to_a_focused_field_keeps_its_caret(driver, site):
    """Marionette moves the caret only when it focuses the element itself."""
    driver.get(site)
    field = driver.find_element(By.ID, "placed")
    driver.execute_script(
        "const f = document.getElementById('placed'); f.focus();"
        " f.setSelectionRange(0, 0);")
    field.send_keys("Z")
    assert field.get_attribute("value") == "Zabcd"


def test_send_keys_to_what_cannot_take_the_focus_is_refused(driver, site):
    driver.get(site)
    with pytest.raises(exc.ElementNotInteractableException,
                       match=r'Element <div id="plain"> is not reachable by keyboard'):
        driver.find_element(By.ID, "plain").send_keys("lost")


def test_a_click_that_unloads_the_page_waits_for_the_new_one(driver, site):
    driver.get(site)
    driver.find_element(By.ID, "slow").click()
    # Implicit wait is 0: the very next read must see the new page, loaded -
    # the normal strategy waits for `load`, which here waits for the image.
    assert driver.execute_script("return document.readyState") == "complete"
    assert driver.title == "slow page"
    assert driver.find_element(By.TAG_NAME, "body").text == "arrived"


@pytest.mark.wall_clock
def test_a_click_that_unloads_nothing_returns_at_once(driver, site):
    driver.get(site)
    button = driver.find_element(By.ID, "noop")
    began = time.monotonic()
    button.click()
    clicked = time.monotonic() - began
    assert driver.execute_script("return window.clicked") == 1
    # The click itself takes a human hand's time; what must not be added is a
    # page-load wait. The unload window is 50 ms.
    assert clicked < 5, clicked


def test_a_click_on_a_hash_link_does_not_wait_for_a_load(driver, site):
    driver.get(site)
    driver.find_element(By.ID, "hash").click()
    assert driver.current_url.endswith("#here")
