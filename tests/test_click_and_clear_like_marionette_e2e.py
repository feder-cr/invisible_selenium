"""`click` and `clear` try once, with Marionette's checks, on a real engine.

Until 0.3.7 both went through the engine's Playwright loop, which waits for an
element to be visible, enabled, stable and the hit target and tries again
until a timeout. geckodriver does not: Marionette's `webdriverClickElement` and
`clearElement` (interaction.sys.mjs) check once and raise what they found. So a
covered element waited the whole timeout before failing, a disabled button was
refused where geckodriver clicks it, and an empty field was focused and blurred
by a `clear` that Marionette leaves alone.
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.by import By

pytestmark = pytest.mark.e2e

PAGE = b"""<!doctype html><html><head><title>actions</title></head>
<body style="margin:0">
<input id=file type=file>
<button id=disabled disabled>disabled</button>
<div style="position:relative;width:200px;height:40px">
  <button id=covered onclick="window.coveredClicks = 1">covered</button>
  <div id=overlay style="position:absolute;left:0;top:0;width:200px;height:40px"></div>
</div>
<button id=nopointer style="pointer-events: none">no pointer events</button>
<button id=offscreen style="position:fixed;top:-200px">off the screen</button>
<select id=sel><option id=opta>a</option><option id=optb>b</option>
  <option id=optc disabled>c</option></select>
<input id=dis disabled value=x>
<input id=ro readonly value=x>
<div id=plain>plain</div>
<input id=empty value="">
<input id=full value="text">
<div style="height:3000px"></div>
<button id=below onclick="window.belowClicks = 1">below</button>
<div style="height:600px"></div>
<script>
  window.focuses = 0;
  document.getElementById('empty').addEventListener('focus', () => window.focuses++);
  window.changes = 0;
  document.getElementById('full').addEventListener('change', () => window.changes++);
</script>
</body></html>"""


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

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
    d = webdriver.Firefox(seed=4245, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


@pytest.fixture
def page(driver, site):
    driver.get(site)
    return driver


#: A refusal is answered by one check. The loop it replaced waited at least
#: five seconds before giving up, so anything near that is the loop.
AT_ONCE_S = 2.5


def test_a_file_input_is_not_clicked(page):
    with pytest.raises(exc.InvalidArgumentException,
                       match=r"Cannot click <input type=file> elements"):
        page.find_element(By.ID, "file").click()


@pytest.mark.wall_clock
def test_a_covered_element_is_refused_at_once(page):
    button = page.find_element(By.ID, "covered")
    began = time.monotonic()
    with pytest.raises(exc.ElementClickInterceptedException,
                       match=r'Element <button id="covered"> is not clickable at '
                             r'point \(\d+,\d+\) because another element '
                             r'<div id="overlay"> obscures it'):
        button.click()
    assert time.monotonic() - began < AT_ONCE_S
    assert page.execute_script("return window.coveredClicks") is None


def test_an_element_without_pointer_events_is_refused_and_says_why(page):
    with pytest.raises(exc.ElementClickInterceptedException,
                       match=r'Element <button id="nopointer"> is not clickable at '
                             r'point \(\d+,\d+\) because it does not have pointer '
                             r'events enabled, and element <\w+[^>]*> would '
                             r'receive the click instead'):
        page.find_element(By.ID, "nopointer").click()


@pytest.mark.wall_clock
def test_a_disabled_button_is_clicked_without_an_error(page):
    """Marionette's click has no enabled check: the press goes out, and a
    disabled button does what a disabled button does with it, nothing."""
    began = time.monotonic()
    page.find_element(By.ID, "disabled").click()
    assert time.monotonic() - began < AT_ONCE_S + 2.0


def test_what_cannot_be_scrolled_into_view_is_refused(page):
    with pytest.raises(exc.ElementNotInteractableException,
                       match=r'Element <button id="offscreen"> could not be '
                             r'scrolled into view'):
        page.find_element(By.ID, "offscreen").click()


def test_a_click_scrolls_the_element_to_the_bottom_of_the_view(page):
    """`dom.scrollIntoView`: block end, so the element's bottom edge sits on
    the viewport's."""
    page.find_element(By.ID, "below").click()
    assert page.execute_script("return window.belowClicks") == 1
    bottom, height = page.execute_script(
        "const r = document.getElementById('below').getBoundingClientRect();"
        " return [r.bottom, window.innerHeight];")
    assert abs(bottom - height) <= 1


def test_clicking_an_option_chooses_it_and_a_disabled_one_is_left(page):
    page.find_element(By.ID, "optb").click()
    assert page.execute_script("return document.getElementById('sel').value") == "b"
    page.find_element(By.ID, "optc").click()
    assert page.execute_script("return document.getElementById('sel').value") == "b"


@pytest.mark.parametrize("element_id, message", [
    ("dis", r'Element is disabled: <input id="dis">'),
    ("ro", r'Element is read-only: <input id="ro">'),
    ("plain", r'Unable to clear element that cannot be edited: <div id="plain">'),
])
@pytest.mark.wall_clock
def test_clear_refuses_at_once_what_cannot_be_cleared(page, element_id, message):
    element = page.find_element(By.ID, element_id)
    began = time.monotonic()
    with pytest.raises(exc.InvalidElementStateException, match=message):
        element.clear()
    assert time.monotonic() - began < AT_ONCE_S


def test_clear_leaves_an_empty_field_alone(page):
    """Marionette returns before focusing a field that is empty and valid."""
    page.find_element(By.ID, "empty").clear()
    assert page.execute_script("return window.focuses") == 0


def test_clear_empties_a_field_and_fires_change(page):
    field = page.find_element(By.ID, "full")
    field.clear()
    assert field.get_attribute("value") == ""
    assert page.execute_script("return window.changes") == 1
