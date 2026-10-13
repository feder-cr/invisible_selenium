"""Dialogs and frames as Marionette answers them, on a real engine.

Every expectation here was answered by the original - Selenium 4.51,
geckodriver 0.37.1 and retail Firefox 151 - on 2026-10-13. What 0.4.0 did
instead:

- a script that opened an alert waited for an answer nobody gave, to the
  script timeout (~31 s), where Marionette answers None at once and leaves
  the alert open;
- a page that alerted while it loaded held `get` to the page load timeout,
  where Marionette's wait ends on the dialog;
- a `beforeunload` the page asked held the navigation, and `close()` never
  ran it; Marionette accepts it at once, and `close()` runs it;
- the dismissed dialog was reported as "Dismissed user prompt dialog: ...",
  and `close`, `new_window`, the window rect, `default_content` and
  `submit` ran under an open dialog without dismissing it;
- `frame(N)` counted `iframe, frame` elements with the implicit wait, missed
  an iframe in a shadow root, took any frame element of any document, and
  answered a frame that had gone as if it were there;
- a dialog that opened during an implicit wait was waited through.
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.by import By

pytestmark = pytest.mark.e2e

PAGES = {
    "/alerting": b"<!doctype html><title>a</title><p id=p>p</p>"
                 b"<script>alert('loading')</script>",
    "/bu": b"<!doctype html><title>bu</title><input id=i><script>"
           b"addEventListener('beforeunload', e => { localStorage.bu = '1';"
           b" e.preventDefault(); e.returnValue = 'x'; })</script>",
    "/framed": b"<!doctype html><title>fr</title><div id=d></div>"
               b"<iframe id=f src=/plain></iframe><iframe id=g src=/other></iframe>",
    "/nested": b"<!doctype html><iframe id=n src=/framed></iframe>",
    "/shadow": b"<!doctype html><div id=h></div><iframe id=plain src=/plain></iframe>"
               b"<script>const r = document.getElementById('h').attachShadow("
               b"{mode: 'open'}); r.innerHTML = '<iframe src=/other></iframe>';</script>",
    "/other": b"<!doctype html><title>other</title><p>other</p>",
}
PLAIN = b"<!doctype html><title>plain</title><p id=p>plain</p><form><input id=fi></form>"


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path.split("?")[0], PLAIN)
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
    d = webdriver.Firefox(seed=4271, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


@pytest.fixture
def page(driver, site):
    try:
        driver.switch_to.alert.dismiss()
    except exc.NoAlertPresentException:
        pass
    first = driver.window_handles[0]
    for handle in driver.window_handles[1:]:
        driver.switch_to.window(handle)
        driver.close()
    driver.switch_to.window(first)
    driver.switch_to.default_content()
    driver.implicitly_wait(0)
    driver.set_page_load_timeout(300)
    driver.get(site)
    yield driver


def _open_alert(d, kind="alert"):
    d.execute_script("setTimeout(() => %s('hi'), 0)" % kind)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            d.switch_to.alert
            return
        except exc.NoAlertPresentException:
            time.sleep(0.05)
    raise AssertionError("the dialog never opened")


def _dismissed(d, kind="alert"):
    return pytest.raises(exc.UnexpectedAlertPresentException,
                         match=r'Unexpected %s dialog detected\. Performed '
                               r'handler "dismiss"' % kind)


# ── c. a dialog inside a script ─────────────────────────────────────────────
def test_a_script_that_alerts_answers_none_at_once(page):
    began = time.monotonic()
    assert page.execute_script("alert('hi'); return 5") is None
    assert time.monotonic() - began < 3
    assert page.switch_to.alert.text == "hi"
    with _dismissed(page) as caught:
        page.title
    assert caught.value.alert_text == "hi"
    with pytest.raises(exc.NoAlertPresentException):
        page.switch_to.alert


def test_an_asynchronous_script_ends_when_a_dialog_opens(page):
    page.execute_script("setTimeout(() => alert('later'), 300)")
    began = time.monotonic()
    assert page.execute_async_script(
        "setTimeout(() => arguments[0](7), 3000)") is None
    assert time.monotonic() - began < 2
    assert page.switch_to.alert.text == "later"


# ── f. which commands meet the dialog ───────────────────────────────────────
@pytest.mark.parametrize("command", [
    lambda d: d.close(),
    lambda d: d.switch_to.default_content(),
    lambda d: d.switch_to.frame(0),
    lambda d: d.switch_to.new_window("tab"),
    lambda d: d.get_window_rect(),
    lambda d: d.maximize_window(),
    lambda d: d.execute_script("return 1"),
    lambda d: d.execute_async_script("arguments[0](2)"),
    lambda d: d.find_element(By.ID, "fi").submit(),
], ids=["close", "default_content", "frame", "new_window", "window_rect",
        "maximize", "execute_script", "execute_async_script", "submit"])
def test_a_command_that_meets_the_dialog_dismisses_it(page, command):
    _open_alert(page)
    with _dismissed(page):
        command(page)
    with pytest.raises(exc.NoAlertPresentException):
        page.switch_to.alert
    assert len(page.window_handles) == 1


@pytest.mark.parametrize("command", [
    lambda d: d.window_handles,
    lambda d: d.current_window_handle,
    lambda d: d.switch_to.window(d.current_window_handle),
    lambda d: d.switch_to.parent_frame(),
    lambda d: d.timeouts,
], ids=["window_handles", "current_window_handle", "switch_to_window",
        "parent_frame", "timeouts"])
def test_a_command_that_does_not_meet_the_dialog_leaves_it(page, command):
    _open_alert(page)
    command(page)
    assert page.switch_to.alert.text == "hi"


@pytest.mark.parametrize("kind", ["confirm", "prompt"])
def test_the_dialog_is_named_by_its_type(page, kind):
    _open_alert(page, kind)
    with _dismissed(page, kind):
        page.title


def test_a_dialog_during_an_implicit_wait_ends_the_find(page):
    page.implicitly_wait(5)
    page.execute_script("setTimeout(() => alert('mid'), 500)")
    began = time.monotonic()
    with pytest.raises(exc.WebDriverException,
                       match="^Message: Failed to convert data to an object"):
        page.find_element(By.ID, "never")
    assert time.monotonic() - began < 3
    assert page.switch_to.alert.text == "mid"


# ── d. a dialog while the page loads ────────────────────────────────────────
def test_a_page_that_alerts_while_it_loads_ends_the_wait(page, site):
    page.set_page_load_timeout(10)
    began = time.monotonic()
    page.get(site + "alerting")
    assert time.monotonic() - began < 3
    assert page.switch_to.alert.text == "loading"
    page.switch_to.alert.accept()
    assert page.find_element(By.ID, "p").text == "p"


# ── e. beforeunload ─────────────────────────────────────────────────────────
def test_beforeunload_is_accepted_and_the_navigation_goes_on(page, site):
    page.get(site + "bu")
    page.find_element(By.ID, "i").click()  # sticky activation, which it needs
    began = time.monotonic()
    page.get(site + "other")
    assert time.monotonic() - began < 5
    assert page.current_url == site + "other"
    page.get(site + "bu")
    page.find_element(By.ID, "i").click()
    page.back()
    assert page.current_url == site + "other"


def test_close_runs_beforeunload(page, site):
    first = page.current_window_handle
    page.switch_to.new_window("tab")
    page.get(site + "bu")
    page.execute_script("localStorage.removeItem('bu')")
    page.find_element(By.ID, "i").click()
    page.close()
    page.switch_to.window(first)
    page.get(site + "other")
    assert page.execute_script("return localStorage.bu") == "1"
    assert page.window_handles == [first]


# ── i. frames ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("reference, column", [(-1, 10), (70000, 13), (True, 12),
                                               (1.5, 11)])
def test_a_frame_reference_geckodriver_refuses(page, reference, column):
    with pytest.raises(exc.InvalidArgumentException,
                       match=r"^Message: data did not match any variant of "
                             r"untagged enum FrameId at line 1 column %d" % column):
        page.switch_to.frame(reference)


def test_a_frame_index_counts_the_child_browsing_contexts(page, site):
    page.get(site + "framed")
    with pytest.raises(exc.NoSuchFrameException,
                       match="^Message: Unable to locate frame with index: 5"):
        page.switch_to.frame(5)
    with pytest.raises(exc.NoSuchFrameException,
                       match=r"^Message: Unable to locate frame for element: "
                             r"\[object HTMLDivElement\]"):
        page.switch_to.frame(page.find_element(By.ID, "d"))
    page.switch_to.frame(1)
    assert page.execute_script("return location.pathname") == "/other"
    page.switch_to.frame(None)
    assert page.title == "fr"
    page.get(site + "shadow")
    page.switch_to.frame(1)
    assert page.execute_script("return location.pathname") == "/other"


def test_an_element_of_another_frame_is_not_known_here(page, site):
    page.get(site + "nested")
    page.switch_to.frame(0)
    inner = page.find_element(By.ID, "f")
    page.switch_to.default_content()
    with pytest.raises(exc.NoSuchElementException,
                       match="is not known in the current browsing context"):
        page.switch_to.frame(inner)


def test_a_frame_that_went_is_a_discarded_browsing_context(page, site):
    page.get(site + "framed")
    page.switch_to.frame(0)
    page.execute_script("setTimeout(() => window.frameElement.remove(), 0)")
    time.sleep(0.3)
    for command in (lambda: page.switch_to.frame(0), page.get_cookies,
                    lambda: page.find_element(By.ID, "p")):
        with pytest.raises(exc.NoSuchWindowException,
                           match="^Message: Browsing context has been discarded"):
            command()
    assert page.current_url == site + "framed"
    page.switch_to.parent_frame()
    assert page.title == "fr"


def test_new_window_takes_any_type_and_refuses_what_is_not_a_string(page):
    first = page.current_window_handle
    page.switch_to.new_window("foo")
    assert len(page.window_handles) == 2
    page.close()
    page.switch_to.window(first)
    with pytest.raises(exc.InvalidArgumentException,
                       match=r"^Message: invalid type: integer `1`, expected a "
                             r"string at line 1 column 10"):
        page.switch_to.new_window(1)
