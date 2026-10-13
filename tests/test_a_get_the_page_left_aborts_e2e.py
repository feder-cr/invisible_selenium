"""A `get()` that the page being left aborts waits out the page load timeout,
as geckodriver's does ([B302]).

document.open() stops the ongoing navigation of its browsing context (HTML
spec), and Firefox does so for a WebDriver navigation too. Marionette then
waits on: its listener ends a navigation on a document's DOMContentLoaded or
pageshow only after the page being left has unloaded (`navigate.sys.mjs`,
`seenUnload`), and the page that rewrote itself never unloaded. Measured on
Selenium 4.51, geckodriver 0.37.1 and retail Firefox 151
(`C:/tmp/b230/oracle_b302.py selenium`): with a page load timeout of 20 s,
TimeoutException "Navigation timed out after 20000 ms" three times in three,
the page the rewritten one.

Until firefox-46 our engine dropped that abort and took the document.write()
for the navigation's commit; this test passed there, by that accident (the
commit came, the `load` never did). With the abort reported, `get()` said
"Reached error page" until it waited as Marionette does. The race is made
certain: the
page being left rewrites itself 300 ms after it loads, and the server holds the
next page's response for 1.5 s.
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

from invisible_selenium.common import exceptions as exc

pytestmark = pytest.mark.e2e

OLD = (b"<html><body><p>first</p><script>setTimeout(() => {document.open();"
       b"document.write('<html><body><h1>rewritten</h1></body></html>');"
       b"document.close()}, 300)</script></body></html>")
NEW = b"<html><body><p>new</p></body></html>"
PAGE_LOAD_S = 3


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/new"):
                time.sleep(1.5)
                body = NEW
            else:
                body = OLD
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def handle(self):
            try:
                super().handle()
            except ConnectionError:
                pass  # the browser let go of the response it stopped

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
    d.set_page_load_timeout(PAGE_LOAD_S)
    yield d
    d.quit()


def test_a_get_the_page_left_aborts_waits_out_the_page_load_timeout(driver, site):
    for i in range(2):
        driver.get(site + "old?i=%d" % i)
        began = time.monotonic()
        with pytest.raises(exc.TimeoutException) as e:
            driver.get(site + "new?i=%d" % i)
        took = time.monotonic() - began
        assert e.value.msg == "Navigation timed out after %d ms" % (PAGE_LOAD_S * 1000)
        assert PAGE_LOAD_S - 0.5 <= took < PAGE_LOAD_S + 3, took
        assert driver.current_url == site + "old?i=%d" % i
        assert driver.execute_script("return !!document.querySelector('h1')")
