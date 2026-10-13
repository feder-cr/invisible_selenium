"""`current_url` and the cookies as Marionette answers them, on a real engine.

What 0.4.0 did instead, each one checked below:

- `current_url` evaluated `location.href` in the page, so a page busy in a
  script held it for as long as the script ran (Marionette reads
  `browsingContext.currentURI` in the parent process and answers at once);
- the cookies were the TOP document's, where Marionette's are the current
  frame's (`_getCurrentURL({top: false})`);
- a cookie's path had to be a prefix of the document's, where Marionette
  only asks that the document's path contain it (`cookie.iter`);
- a `secure` cookie was left out of an http document's list, which
  Marionette does not filter on;
- a cookie had `sameSite` only when it had been given one, where Marionette
  always answers it ("None" when unset);
- `get_cookie` answered the first cookie of that name, geckodriver the last;
- `add_cookie` on a document that is not http(s), or for another domain,
  raised with words of its own;
- an expiry past 400 days was kept, where Marionette caps it;
- `delete_cookie("")` was not refused, where Selenium's client refuses it
  (Firefox would delete every cookie).
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.common import exceptions as exc

pytestmark = pytest.mark.e2e

PAGE = b"<!doctype html><html><head><title>p</title></head><body>p</body></html>"

#: Set when the busy page's beacon reaches the server: the page sends it in
#: the task that holds its thread, so from then on the page is busy.
BUSY = threading.Event()


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path.startswith("/busy"):
                BUSY.set()
            self.send_response(204)
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/outer"):
                port = self.server.server_address[1]
                body = (b'<!doctype html><iframe id=f src="http://localhost:%d/inner">'
                        b"</iframe>" % port)
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
    d = webdriver.Firefox(seed=4270, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


@pytest.fixture
def page(driver, site):
    driver.get(site)
    driver.delete_all_cookies()
    yield driver
    driver.switch_to.default_content()


# ── current_url ─────────────────────────────────────────────────────────────
def test_the_current_url_answers_while_the_page_is_busy(page, site):
    # The page sends a beacon and holds its thread for 6 s in the same task,
    # so once the server has the beacon the page is busy, and the url is
    # never asked before it is. A fixed 0.5 s sleep could ask before, and the
    # test passed without testing anything. Not a synchronous request: its
    # wait runs a nested event loop, and a read arriving then was served.
    BUSY.clear()
    page.execute_script(
        "setTimeout(() => { const end = Date.now() + 6000;"
        " navigator.sendBeacon('/busy'); while (Date.now() < end); }, 0)")
    assert BUSY.wait(5), "the busy page's beacon never came"
    began = time.monotonic()
    assert page.current_url == site
    assert time.monotonic() - began < 2.0
    # The page answers again once its script is done.
    assert page.execute_script("return 1") == 1


def test_the_current_url_follows_a_pushed_state_at_once(page, site):
    page.execute_script("history.pushState({}, '', '/pushed')")
    assert page.current_url == site + "pushed"


def test_a_new_tab_is_about_blank(page):
    first = page.current_window_handle
    page.switch_to.new_window("tab")
    try:
        assert page.current_url == "about:blank"
    finally:
        page.close()
        page.switch_to.window(first)


# ── cookies ─────────────────────────────────────────────────────────────────
def test_a_cookie_path_belongs_when_the_document_path_contains_it(page, site):
    page.get(site + "a/b/page")
    page.add_cookie({"name": "inner", "value": "1", "path": "/b"})
    page.add_cookie({"name": "other", "value": "1", "path": "/c"})
    names = {c["name"] for c in page.get_cookies()}
    assert "inner" in names and "other" not in names


def test_a_secure_cookie_is_listed_on_an_http_document(page):
    page.add_cookie({"name": "s", "value": "1", "secure": True})
    cookie = page.get_cookie("s")
    assert cookie is not None and cookie["secure"] is True


def test_the_cookies_are_the_current_frames(page, site):
    port = site.rsplit(":", 1)[1].rstrip("/")
    page.get(site + "outer")
    page.switch_to.frame(page.find_element("id", "f"))
    page.add_cookie({"name": "framed", "value": "1"})
    framed = page.get_cookie("framed")
    assert framed is not None and framed["domain"] == "localhost"
    page.switch_to.default_content()
    assert page.get_cookie("framed") is None
    page.get("http://localhost:%s/inner" % port)
    page.delete_cookie("framed")
    assert page.get_cookie("framed") is None


def test_a_cookie_always_answers_its_same_site(page):
    page.add_cookie({"name": "plain", "value": "1"})
    assert page.get_cookie("plain")["sameSite"] == "None"
    page.add_cookie({"name": "lax", "value": "1", "sameSite": "Lax"})
    assert page.get_cookie("lax")["sameSite"] == "Lax"


def test_get_cookie_answers_the_last_of_that_name(page, site):
    page.get(site + "a/page")
    page.add_cookie({"name": "dup", "value": "root", "path": "/"})
    page.add_cookie({"name": "dup", "value": "deep", "path": "/a"})
    named = [c for c in page.get_cookies() if c["name"] == "dup"]
    assert len(named) == 2
    assert page.get_cookie("dup") == named[-1]


def test_add_cookie_refuses_as_marionette(page, site):
    with pytest.raises(exc.InvalidCookieDomainException,
                       match=r"^Message: Cookies may only be set for the current "
                             r"domain \(127\.0\.0\.1\)"):
        page.add_cookie({"name": "x", "value": "1", "domain": "example.com"})
    with pytest.raises(exc.InvalidArgumentException):
        page.add_cookie({"name": 1, "value": "1"})
    with pytest.raises(exc.InvalidArgumentException):
        page.add_cookie({"value": "1"})
    page.get("about:blank")
    with pytest.raises(exc.InvalidCookieDomainException,
                       match=r"^Message: Document is cookie-averse"):
        page.add_cookie({"name": "x", "value": "1"})


def test_an_expiry_past_four_hundred_days_is_capped(page):
    asked = int(time.time()) + 10 * 365 * 86400
    page.add_cookie({"name": "far", "value": "1", "expiry": asked})
    expiry = page.get_cookie("far")["expiry"]
    assert expiry <= time.time() + 400 * 86400 + 5
    assert expiry >= time.time() + 400 * 86400 - 60


def test_an_empty_cookie_name_is_refused_before_firefox_sees_it(page):
    page.add_cookie({"name": "kept", "value": "1"})
    for name in ("", "   "):
        with pytest.raises(ValueError, match="^Cookie name cannot be empty$"):
            page.delete_cookie(name)
    assert page.get_cookie("kept") is not None
