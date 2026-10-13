"""Alerts, windows and refusals as the original answers them (phase 4).

Every expectation was answered by Selenium 4.51, geckodriver 0.37.1 and
retail Firefox 151 on 2026-10-13 (`C:/tmp/b230/oracle_se_phase4.py`). What
0.4.0 did instead:

- an unknown locator strategy was "unknown locator strategy 'foo'", where
  geckodriver refuses the body in serde's words;
- no dialog was "No dialog is present", and an alert already answered was
  "The dialog is no longer open" or still answered its old text, where the
  original says NoAlertPresentException with no message: its `Alert` is not
  bound to a dialog, every call asks for the one open now;
- the text sent to a prompt was lost when the prompt was accepted through a
  second `switch_to.alert`, the usual way to write it: the page got the
  default value;
- `send_keys` on an alert or a confirm said "is not a prompt", where
  Marionette says "is not interactable";
- a window could not be found by its name, which the Selenium client looks
  for in every window's `window.name` when no handle matches.
"""
from __future__ import annotations

import http.server
import threading

import pytest

from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.by import By
from invisible_selenium.webdriver.support import expected_conditions as EC
from invisible_selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.e2e

#: A dialog or a window shows in well under a second; the waits end as soon as
#: it is there, and this only bounds a run where it never comes.
SHOWS_WITHIN_S = 5

VARIANTS = ("expected one of `css selector`, `link text`, `partial link text`, "
            "`tag name`, `xpath`")
DOC = ("; For documentation on this error, please visit: https://www.selenium"
       ".dev/documentation/webdriver/troubleshooting/errors"
       "#elementnotinteractableexception")


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = (b"<!doctype html><title>named</title><p>named</p>"
                    if self.path.startswith("/named") else
                    b"<!doctype html><title>plain</title><p id=p>plain</p>"
                    b"<a id=l href=/named target=myname>open</a>")
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
    d = webdriver.Firefox(seed=4302, binary_path=firefox_binary, headless=True)
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
    driver.get(site)
    return driver


def _open(d, script):
    # The dialog opens from a timer, after the script has returned, so the
    # test waits for it as a Selenium user does. A fixed 0.4 s sleep was red
    # on a runner with four browsers, where the dialog came later.
    d.execute_script("setTimeout(() => { %s }, 0)" % script)
    WebDriverWait(d, SHOWS_WITHIN_S).until(EC.alert_is_present(),
                                           "the dialog never opened")


def test_an_unknown_strategy_is_refused_in_serde_s_words(page):
    for by, column in (("foo", 15), ("", 12)):
        with pytest.raises(exc.InvalidArgumentException) as e:
            page.find_element(by, "x")
        assert e.value.msg == "unknown variant `%s`, %s at line 1 column %d" % (
            by, VARIANTS, column)
    with pytest.raises(exc.InvalidArgumentException) as e:
        page.find_element(By.ID, "p").find_elements("foo", "x")
    assert e.value.msg == ("unknown variant `foo`, %s at line 1 column 15"
                           % VARIANTS)


def test_no_dialog_and_an_answered_one_are_no_alert_without_a_message(page):
    with pytest.raises(exc.NoAlertPresentException) as e:
        page.switch_to.alert
    assert e.value.msg == ""
    _open(page, "alert('hi')")
    held = page.switch_to.alert
    held.accept()
    for call in (held.accept, held.dismiss, lambda: held.text):
        with pytest.raises(exc.NoAlertPresentException) as e:
            call()
        assert e.value.msg == ""


def test_the_text_sent_to_a_prompt_survives_a_second_alert_object(page):
    _open(page, "window.r = prompt('q', 'dflt');")
    page.switch_to.alert.send_keys("typed")
    page.switch_to.alert.accept()
    assert page.execute_script("return window.r") == "typed"


@pytest.mark.parametrize("kind", ["alert", "confirm"])
def test_send_keys_on_an_alert_or_a_confirm_is_not_interactable(page, kind):
    _open(page, "%s('hi')" % kind)
    with pytest.raises(exc.ElementNotInteractableException) as e:
        page.switch_to.alert.send_keys("x")
    assert e.value.msg == "User prompt of type %s is not interactable%s" % (
        kind, DOC)
    assert page.switch_to.alert.text == "hi"


def test_a_window_is_found_by_its_name(page, site):
    # Opened as a person opens it, by a link: a `window.open` from a script
    # with no click is held by the popup blocker of a real Firefox, which
    # this is; the original opens it only because geckodriver turns the
    # blocker off.
    first = page.current_window_handle
    page.find_element(By.ID, "l").click()
    WebDriverWait(page, SHOWS_WITHIN_S).until(EC.number_of_windows_to_be(2))
    opened = next(h for h in page.window_handles if h != first)
    page.switch_to.window(opened)
    WebDriverWait(page, SHOWS_WITHIN_S).until(EC.title_is("named"))
    page.switch_to.window(first)
    page.switch_to.window("myname")
    assert page.current_window_handle == opened
    assert page.title == "named"
    page.switch_to.window(first)
    with pytest.raises(exc.NoSuchWindowException) as e:
        page.switch_to.window("nosuch")
    assert e.value.msg == "Unable to locate window: nosuch"
    assert page.current_window_handle == first
