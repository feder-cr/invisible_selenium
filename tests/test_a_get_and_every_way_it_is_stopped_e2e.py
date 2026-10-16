"""A `get()` that something stops or replaces on its way answers as
geckodriver's does, for every way a page can ([B302], the class).

Measured on Selenium 4.51, geckodriver 0.37.1 and retail Firefox 151
(`C:/tmp/b230/oracle_selenium_class.py`, page load timeout 5 s, 2026-10-14):

- document.open, window.stop: TimeoutException "Navigation timed out after N
  ms" at the page load timeout, the old page staying. Marionette ends a
  navigation on a document's DOMContentLoaded or pageshow only once the page
  being left has unloaded (`navigate.sys.mjs`, `seenUnload`), and a page that
  stopped the navigation never unloads;
- location.replace, location.assign, a form submit, an iframe navigating the
  top, history.back: get() returns at once, the page where the page sent it
  (the stop unloads it into another document, which ends the wait);
- history.pushState, nothing: get() returns on its page;
- a meta refresh the page adds: get() returns, on its page or on the one the
  refresh names - the engine replays a queued refresh at random on Linux and
  never on Windows ([B305]), so the case asserts that get() returns and is not
  on the page being left, which is what [B302] is about.

Until firefox-46 the engine dropped the stop; with it reported, get() said
"Reached error page" until it waited as Marionette does. Same site (one
process) and another site (`localhost`, a Fission process swap), twice, back
to back; the page being left acts once the server has the get's request, and
the server holds the page asked for 1.5 s, so the get is on its way when the
page acts on any machine. (It acted on a timer 300 ms after its load until a
slow CI runner started the get later than that: nothing was left to stop.)
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.common import exceptions as exc

pytestmark = pytest.mark.e2e

HELD_S = 1.5
PAGE_LOAD_S = 3
ACT = {
    "docopen": "document.open(); document.write('<html><body><h1>rewritten</h1></body></html>'); document.close();",
    "stop": "window.stop();",
    "replace": "location.replace('/other?from=replace');",
    "assign": "location.assign('/other?from=assign');",
    "pushstate": "history.pushState({}, '', '/pushed');",
    "back": "history.back();",
    "submit": "document.getElementById('f').submit();",
    "meta": "const m = document.createElement('meta'); m.httpEquiv = 'refresh'; m.content = '0;url=/other?from=meta'; document.head.appendChild(m);",
    "iframe_top": None,
    "none": "",
}
#: geckodriver's answer to each kind, and where the page then is.
EXPECT = {
    "docopen": ("timeout", "/old"),
    "stop": ("timeout", "/old"),
    "replace": ("returned", "/other?from=replace"),
    "assign": ("returned", "/other?from=assign"),
    "back": ("returned", "/start"),
    "submit": ("returned", "/other?from=submit"),
    "iframe_top": ("returned", "/other?from=iframe"),
    "pushstate": ("landed", None),
    #: The engine's race, not an answer of ours: [B305].
    "meta": ("landed-or-refreshed", "/other?from=meta"),
    "none": ("landed", None),
}


#: The queries of the goto requests the server has had since it served the
#: page being left with the same query.
ARRIVED = set()


def _when_the_goto_arrives(key, act):
    """Script that asks the server every 50 ms whether the goto's request has
    arrived, and runs `act` once it has."""
    return ("const w = setInterval(() => fetch('/act?%s', {cache: 'no-store'})"
            ".then(r => r.text()).then(t => { if (t === 'go') { clearInterval(w); %s } }),"
            " 50);" % (key, act))


def _old_page(kind, key):
    if kind == "iframe_top":
        inner = _when_the_goto_arrives(key, "top.location = '/other?from=iframe';")
        return ("<html><body><p>old</p><iframe srcdoc=\"<script>%s</script>\"></iframe>"
                "</body></html>" % inner.replace('"', "&quot;"))
    return ("<html><head></head><body><p>old</p><form id=f action='/other' method=get>"
            "<input name=from value=submit></form><script>%s</script></body></html>"
            % _when_the_goto_arrives(key, ACT[kind]))


@pytest.fixture(scope="module")
def server():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path == "/new":
                ARRIVED.add(query)
                time.sleep(HELD_S)
                body = "<html><body><p>new</p></body></html>"
            elif path == "/act":
                body = "go" if query in ARRIVED else "wait"
            elif path == "/old":
                # Both sites run with the same query: the page waits for a
                # goto made after it was served.
                ARRIVED.discard(query)
                body = _old_page(query.split("k=")[1].split("&")[0], query)
            else:
                body = "<html><body><p>%s</p></body></html>" % path
            body = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def handle(self):
            try:
                super().handle()
            except ConnectionError:
                pass  # the browser let go of a response it stopped

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


@pytest.fixture(scope="module")
def driver(firefox_binary):
    from invisible_selenium import webdriver
    d = webdriver.Firefox(seed=4302, binary_path=firefox_binary, headless=True)
    d.set_page_load_timeout(PAGE_LOAD_S)
    yield d
    d.quit()


@pytest.mark.wall_clock
@pytest.mark.parametrize("kind", list(ACT))
def test_a_get_stopped_on_its_way_answers_as_geckodriver(driver, server, kind):
    same = "http://127.0.0.1:%d" % server
    cross = "http://localhost:%d" % server
    answer, end = EXPECT[kind]
    for site, target_base in (("same", same), ("cross", cross)):
        for i in range(2):
            driver.get(same + "/start?k=%s&i=%d" % (kind, i))
            driver.get(same + "/old?k=%s&i=%d" % (kind, i))
            target = target_base + "/new?k=%s&i=%d" % (kind, i)
            began = time.monotonic()
            error = None
            try:
                driver.get(target)
            except exc.WebDriverException as e:
                error = e
            took = time.monotonic() - began
            where = (kind, site, i, repr(error), took, driver.current_url)
            if answer == "timeout":
                assert isinstance(error, exc.TimeoutException), where
                assert error.msg == "Navigation timed out after %d ms" % (PAGE_LOAD_S * 1000), where
                assert PAGE_LOAD_S - 0.5 <= took < PAGE_LOAD_S + 3, where
                assert driver.current_url == same + "/old?k=%s&i=%d" % (kind, i), where
            elif answer == "returned":
                assert error is None, where
                assert took < HELD_S, where
                expected = same + end
                if end == "/start":
                    expected = same + "/start?k=%s&i=%d" % (kind, i)
                assert driver.current_url == expected, where
            else:
                assert error is None, where
                assert took >= HELD_S - 0.1, where
                if answer == "landed-or-refreshed":
                    assert driver.current_url in (target, same + end), where
                else:
                    assert driver.current_url == target, where
                assert driver.current_url != same + "/old?k=%s&i=%d" % (kind, i), where
